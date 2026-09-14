import json
import re
from collections import Counter

from django.utils.timezone import localdate

from ai_services.clients.cloudflare_ai_client import CloudflareAIClient
from customer_support.models import SupportMessage


TOPIC_KEYWORDS = {
    "Delivery": (
        "deliver", "delivery", "shipping", "ship", "arrive", "arrival",
        "courier", "tracking", "توصيل", "شحن", "يوصل",
    ),
    "Pricing": (
        "price", "pricing", "cost", "expensive", "cheap", "discount",
        "سعر", "غالي", "رخيص", "خصم",
    ),
    "Product information": (
        "ingredient", "ingredients", "contain", "size", "flavour",
        "flavor", "مكونات", "حجم", "نكهة",
    ),
    "Availability": (
        "available", "availability", "in stock", "sold out", "out of stock",
        "متوفر", "توفر", "نفد",
    ),
    "Refunds": (
        "refund", "money back", "استرجاع المبلغ", "استرداد",
    ),
    "Returns": (
        "return", "exchange", "استبدال", "إرجاع",
    ),
    "Opening hours": (
        "open", "hours", "closing", "ساعات", "مفتوح",
    ),
    "Promotions": (
        "promo", "offer", "coupon", "sale", "عرض", "كوبون",
    ),
}

POSITIVE_WORDS = (
    "thanks", "thank", "great", "love", "excellent", "good", "perfect",
    "شكرا", "ممتاز", "رائع", "حلو",
)
NEGATIVE_WORDS = (
    "late", "delay", "expensive", "broken", "bad", "worst", "angry",
    "missing", "wrong", "سيء", "غالي", "متأخر", "مشكلة",
)
QUESTION_HINTS = (
    "when", "how", "is ", "does", "can ", "where", "what", "why",
    "متى", "كيف", "هل", "وين", "كم",
)
MIN_CUSTOMER_MESSAGES = 3
MAX_BATCH_ITEMS = 40
MAX_TEXT_CHARS = 280


class CustomerVoiceAnalyzer:
    """Customer-message intelligence. Counts stay in Python."""

    def __init__(self, llm=None, retriever=None):
        self._llm = llm
        self._retriever = retriever

    @property
    def llm(self):
        if self._llm is None:
            self._llm = CloudflareAIClient()
        return self._llm

    @property
    def retriever(self):
        if self._retriever is None:
            from ai_services.rag.retriever import Retriever

            self._retriever = Retriever()
        return self._retriever

    def gather_customer_messages(self, company, campaign=None):
        queryset = (
            SupportMessage.objects
            .filter(
                conversation__company=company,
                sender="Customer",
            )
            .select_related("conversation")
            .order_by("created_at")
        )
        filtered = False
        if campaign is not None and (campaign.start_date or campaign.end_date):
            messages = []
            for message in queryset:
                day = localdate(message.created_at)
                if campaign.start_date and day < campaign.start_date:
                    continue
                if campaign.end_date and day > campaign.end_date:
                    continue
                messages.append(message)
            filtered = True
            return messages, filtered
        return list(queryset), filtered

    def analyze(
        self,
        company,
        campaign=None,
        use_ai=False,
        include_knowledge_gaps=False,
    ):
        messages, filtered = self.gather_customer_messages(
            company,
            campaign=campaign,
        )
        conversation_ids = {
            message.conversation_id for message in messages
        }
        if not messages:
            return {
                "empty": True,
                "insufficient_data": True,
                "conversation_count": 0,
                "customer_message_count": 0,
                "topics": [],
                "sentiment": self._empty_sentiment(),
                "concerns": [],
                "questions": [],
                "knowledge_gaps": [],
                "ai_summary": None,
                "ai_error": None,
                "filtered_to_campaign_dates": filtered,
            }

        records = [
            {
                "id": message.id,
                "text": (message.message_text or "").strip(),
            }
            for message in messages
            if (message.message_text or "").strip()
        ]
        classified = [self._lexical_item(item) for item in records]
        if use_ai and records:
            try:
                classified = self._merge_ai_classification(records, classified)
            except Exception:
                pass

        result = self._aggregate(
            classified,
            conversation_count=len(conversation_ids),
            customer_message_count=len(records),
        )
        result["empty"] = False
        result["filtered_to_campaign_dates"] = filtered
        result["insufficient_data"] = (
            len(records) < MIN_CUSTOMER_MESSAGES
        )
        result["knowledge_gaps"] = []
        result["ai_summary"] = None
        result["ai_error"] = None

        if include_knowledge_gaps and not result["insufficient_data"]:
            result["knowledge_gaps"] = self.evaluate_knowledge_gaps(
                company.id,
                result.get("questions") or [],
            )

        if use_ai and not result["insufficient_data"]:
            try:
                result["ai_summary"] = self.summarize(result)
            except Exception:
                result["ai_error"] = (
                    "Customer Voice AI summary could not be generated. "
                    "Deterministic analytics are still available."
                )
        return result

    def _lexical_item(self, item):
        text = item["text"]
        lowered = text.lower()
        topic = "Other"
        for name, keywords in TOPIC_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                topic = name
                break
        pos = sum(1 for word in POSITIVE_WORDS if word in lowered)
        neg = sum(1 for word in NEGATIVE_WORDS if word in lowered)
        if pos and neg:
            sentiment = "Mixed"
        elif pos:
            sentiment = "Positive"
        elif neg:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
        concern = topic if topic != "Other" and sentiment in (
            "Negative",
            "Mixed",
        ) else (topic if topic != "Other" else None)
        is_question = (
            "?" in text
            or any(lowered.startswith(hint) or f" {hint}" in lowered
                   for hint in QUESTION_HINTS)
        )
        question_theme = topic if is_question and topic != "Other" else (
            self._short_theme(text) if is_question else None
        )
        return {
            "id": item["id"],
            "topic": topic,
            "sentiment": sentiment,
            "concern": concern,
            "question_theme": question_theme,
        }

    @staticmethod
    def _short_theme(text):
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) > 72:
            cleaned = cleaned[:69].rstrip() + "..."
        return cleaned

    def _merge_ai_classification(self, records, fallback):
        batch = records[:MAX_BATCH_ITEMS]
        payload = [
            {
                "id": item["id"],
                "text": item["text"][:MAX_TEXT_CHARS],
            }
            for item in batch
        ]
        prompt = f"""
Classify customer support messages for marketing analytics.
Return JSON only. Do not invent extra messages.
Use short topic labels. Sentiment must be Positive, Neutral, Negative, or Mixed.
Normalize similar concerns and questions into shared labels.

Messages:
{json.dumps(payload, ensure_ascii=False)}

Return:
{{
  "items": [
    {{
      "id": 1,
      "topic": "...",
      "sentiment": "Neutral",
      "concern": "... or empty",
      "question_theme": "... or empty"
    }}
  ]
}}
""".strip()
        raw = self.llm.generate(
            prompt=prompt,
            system_prompt=(
                "You classify customer messages. Never calculate percentages. "
                "Return JSON only."
            ),
            temperature=0.2,
            max_tokens=1200,
        )
        data = self._parse_json(raw)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return fallback
        by_id = {item["id"]: item for item in fallback}
        for row in items:
            if not isinstance(row, dict):
                continue
            try:
                item_id = int(row.get("id"))
            except (TypeError, ValueError):
                continue
            current = by_id.get(item_id)
            if not current:
                continue
            topic = str(row.get("topic") or "").strip() or current["topic"]
            sentiment = str(row.get("sentiment") or "").strip().title()
            if sentiment not in ("Positive", "Neutral", "Negative", "Mixed"):
                sentiment = current["sentiment"]
            concern = str(row.get("concern") or "").strip() or None
            question = str(row.get("question_theme") or "").strip() or None
            by_id[item_id] = {
                "id": item_id,
                "topic": topic,
                "sentiment": sentiment,
                "concern": concern,
                "question_theme": question,
            }
        return [by_id[item["id"]] for item in fallback]

    def _aggregate(self, classified, conversation_count, customer_message_count):
        total = len(classified) or 1
        topic_counter = Counter(item["topic"] for item in classified)
        sentiment_counter = Counter(item["sentiment"] for item in classified)
        concern_counter = Counter(
            item["concern"] for item in classified if item.get("concern")
        )
        question_counter = Counter(
            item["question_theme"]
            for item in classified
            if item.get("question_theme")
        )

        def ranked(counter):
            rows = []
            for name, count in counter.most_common(8):
                rows.append(
                    {
                        "label": name,
                        "count": count,
                        "percentage": round((count / total) * 100, 1),
                    }
                )
            return rows

        sentiment = {}
        for label in ("Positive", "Neutral", "Negative", "Mixed"):
            count = sentiment_counter.get(label, 0)
            sentiment[label] = {
                "count": count,
                "percentage": round((count / total) * 100, 1),
            }
        return {
            "conversation_count": conversation_count,
            "customer_message_count": customer_message_count,
            "topics": ranked(topic_counter),
            "sentiment": sentiment,
            "concerns": ranked(concern_counter),
            "questions": ranked(question_counter),
        }

    def _empty_sentiment(self):
        return {
            label: {"count": 0, "percentage": 0}
            for label in ("Positive", "Neutral", "Negative", "Mixed")
        }

    def evaluate_knowledge_gaps(self, company_id, questions, limit=5):
        from ai_services.analytics.knowledge_support import (
            classify_hits,
            parse_query_results,
        )

        gaps = []
        for item in questions[:limit]:
            theme = item.get("label") or ""
            if not theme:
                continue
            hits = []
            has_distances = False
            space = "l2"
            try:
                evidence = None
                retrieve_evidence = getattr(
                    self.retriever,
                    "retrieve_evidence",
                    None,
                )
                if callable(retrieve_evidence):
                    raw = retrieve_evidence(
                        theme,
                        company_id,
                        n_results=3,
                    )
                    if isinstance(raw, dict):
                        evidence = raw
                if isinstance(evidence, dict) and isinstance(
                    evidence.get("hits"),
                    list,
                ):
                    hits = evidence.get("hits") or []
                    has_distances = bool(evidence.get("has_distances"))
                    space = evidence.get("space") or "l2"
                elif isinstance(evidence, dict):
                    hits, has_distances = parse_query_results(evidence)
                else:
                    results = self.retriever.retrieve(
                        theme,
                        company_id,
                        n_results=3,
                    )
                    hits, has_distances = parse_query_results(results)
            except Exception:
                hits, has_distances = [], False
            classified = classify_hits(hits, has_distances, space=space)
            gaps.append(
                {
                    "theme": theme,
                    "related_questions": item.get("count") or 0,
                    "knowledge_support": classified["knowledge_support"],
                    "relevance_label": classified["relevance_label"],
                    "retrieved_chunks": classified["retrieved_chunks"],
                    "retrieved_documents": classified["retrieved_documents"],
                    "classification_basis": classified["classification_basis"],
                }
            )
        return gaps

    def summarize(self, aggregated):
        payload = {
            "conversation_count": aggregated.get("conversation_count"),
            "customer_message_count": aggregated.get("customer_message_count"),
            "topic_counts": aggregated.get("topics"),
            "sentiment_counts": aggregated.get("sentiment"),
            "recurring_concerns": aggregated.get("concerns"),
            "common_question_themes": aggregated.get("questions"),
            "knowledge_gaps": aggregated.get("knowledge_gaps"),
        }
        prompt = f"""
Interpret this customer-voice analytics JSON for a Marketing Specialist.
Do not invent counts. Do not calculate new percentages.
Use cautious language.

Data:
{json.dumps(payload, ensure_ascii=False)}

Return JSON:
{{
  "summary": "...",
  "main_interests": ["..."],
  "friction_points": ["..."],
  "knowledge_recommendations": ["..."],
  "marketing_recommendations": ["..."]
}}
""".strip()
        raw = self.llm.generate(
            prompt=prompt,
            system_prompt=(
                "You interpret already-calculated customer analytics. "
                "Never invent numbers. Return JSON only."
            ),
            temperature=0.3,
            max_tokens=700,
        )
        data = self._parse_json(raw)
        if not isinstance(data, dict):
            raise ValueError("Customer voice summary was not a JSON object.")

        def as_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            text = str(value).strip()
            return [text] if text else []

        summary = str(data.get("summary") or "").strip()
        if not summary:
            raise ValueError("Customer voice summary was missing.")
        return {
            "summary": summary,
            "main_interests": as_list(data.get("main_interests"))[:5],
            "friction_points": as_list(data.get("friction_points"))[:5],
            "knowledge_recommendations": as_list(
                data.get("knowledge_recommendations")
            )[:4],
            "marketing_recommendations": as_list(
                data.get("marketing_recommendations")
            )[:4],
        }

    @staticmethod
    def _parse_json(raw_text):
        text = str(raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE)
            text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Response was not valid JSON.")
        data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise ValueError("Response was not a JSON object.")
        return data
