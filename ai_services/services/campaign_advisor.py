import json
import re

from ai_services.clients.cloudflare_ai_client import CloudflareAIClient


class CampaignAdvisor:
    """Grounded campaign recommendations from existing analytics only."""

    def __init__(self, llm=None):
        self.llm = llm or CloudflareAIClient()

    def _metrics_payload(self, campaign, summary):
        summary = summary or {}
        payload = {
            "campaign_name": campaign.campaign_name,
            "platform": campaign.platform,
            "status": campaign.status,
        }

        if campaign.budget is not None:
            payload["budget"] = str(campaign.budget)

        metric_keys = (
            "total_views",
            "total_clicks",
            "average_ctr",
            "average_engagement_rate",
            "total_engagement",
            "best_platform",
        )

        for key in metric_keys:
            if key in summary and summary[key] not in (None, ""):
                payload[key] = summary[key]

        return payload

    def _insufficient(self):
        return {
            "performance_insight": (
                "There is insufficient campaign performance data "
                "to produce a grounded recommendation."
            ),
            "strengths": [],
            "weaknesses": [
                "No recorded views, clicks, or engagement metrics were supplied."
            ],
            "recommended_actions": [
                "Add campaign performance records, then generate recommendations again."
            ],
            "insufficient_data": True,
        }

    def _parse_response(self, raw_text):
        text = str(raw_text or "").strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE)
            text = re.sub(r"```$", "", text).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise ValueError("Advisor response was not valid JSON.")

        data = json.loads(text[start:end + 1])

        if not isinstance(data, dict):
            raise ValueError("Advisor response was not a JSON object.")

        def as_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return [
                    str(item).strip()
                    for item in value
                    if str(item).strip()
                ]
            text_value = str(value).strip()
            return [text_value] if text_value else []

        insight = str(data.get("performance_insight") or "").strip()
        strengths = as_list(data.get("strengths"))
        weaknesses = as_list(data.get("weaknesses"))
        actions = as_list(data.get("recommended_actions"))[:4]

        if not insight:
            raise ValueError("Advisor response was missing a performance insight.")

        return {
            "performance_insight": insight,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommended_actions": actions,
            "insufficient_data": False,
        }

    def generate(self, campaign, summary):
        payload = self._metrics_payload(campaign, summary)

        has_metrics = any(
            key in payload
            for key in (
                "total_views",
                "total_clicks",
                "average_ctr",
                "total_engagement",
            )
        )

        if not has_metrics:
            return self._insufficient()

        system_prompt = (
            "You are an AI marketing performance advisor. "
            "Use only the supplied metrics. Never invent numbers. "
            "Return JSON only."
        )

        prompt = f"""
Analyze ONLY the campaign metrics supplied below.

Do not invent numbers or claim data that is not provided.
Return concise, actionable recommendations for a Marketing Manager.

Identify:
1. overall performance insight
2. strengths
3. weaknesses
4. 2–4 recommended actions

When metrics are missing or insufficient, explicitly say there is insufficient data.
Do not recommend unsupported changes as facts.

Campaign metrics JSON:
{json.dumps(payload, ensure_ascii=False)}

Return JSON with this exact shape:
{{
  "performance_insight": "...",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "recommended_actions": ["...", "..."]
}}
""".strip()

        raw = self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=700,
        )

        return self._parse_response(raw)
