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

        objective = str(getattr(campaign, "objective", "") or "").strip()
        if objective:
            payload["campaign_objective"] = objective

        metric_keys = (
            "total_views",
            "total_clicks",
            "total_impressions",
            "average_ctr",
            "ctr_basis",
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

        insight = str(
            data.get("performance_insight")
            or data.get("executive_summary")
            or ""
        ).strip()
        strengths = as_list(data.get("strengths"))
        weaknesses = as_list(data.get("weaknesses"))
        actions = as_list(data.get("recommended_actions"))[:5]

        if not insight:
            raise ValueError("Advisor response was missing a performance insight.")

        what_worked = as_list(data.get("what_worked")) or strengths
        underperformed = (
            as_list(data.get("what_underperformed"))
            or weaknesses
        )
        learning = (
            as_list(data.get("learning_for_next_campaign"))
            or as_list(data.get("next_campaign_learning"))
            or actions
        )
        interpretation = (
            as_list(data.get("likely_interpretation"))
            or as_list(data.get("interpretation"))
        )
        combined_actions = as_list(data.get("combined_actions"))[:5]
        if not combined_actions:
            combined_actions = as_list(
                data.get("combined_recommended_actions")
            )[:5]

        return {
            "performance_insight": insight,
            "executive_summary": str(
                data.get("executive_summary") or insight
            ).strip(),
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommended_actions": actions,
            "what_worked": what_worked,
            "what_underperformed": underperformed,
            "learning_for_next_campaign": learning,
            "interpretation": interpretation,
            "combined_insight": str(data.get("combined_insight") or "").strip(),
            "combined_actions": combined_actions,
            "insufficient_data": False,
        }

    def _qualitative_rating(self, summary):
        summary = summary or {}
        views = summary.get("total_views")
        ctr = summary.get("average_ctr")
        engagement_rate = summary.get("average_engagement_rate")

        try:
            views_value = float(views) if views not in (None, "") else 0.0
        except (TypeError, ValueError):
            views_value = 0.0

        def as_float(value):
            try:
                if value in (None, ""):
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None

        ctr_value = as_float(ctr)
        engagement_value = as_float(engagement_rate)

        if views_value <= 0 and ctr_value is None and engagement_value is None:
            return None, ""

        if (
            (ctr_value is not None and ctr_value >= 2)
            or (engagement_value is not None and engagement_value >= 3)
        ):
            rating = "Strong"
        elif (
            (ctr_value is not None and ctr_value >= 0.8)
            or (engagement_value is not None and engagement_value >= 1.5)
        ):
            rating = "Moderate"
        else:
            rating = "Needs Improvement"

        basis = (
            "Derived from recorded CTR and engagement rate only. "
            "No stored numeric KPI targets were used."
        )
        return rating, basis

    def generate(
        self,
        campaign,
        summary,
        strategy_context=None,
        intelligence=None,
        customer_voice=None,
    ):
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
            result = self._insufficient()
            result["overall_evaluation"] = None
            result["evaluation_basis"] = (
                "A strategy evaluation is not available "
                "without recorded performance metrics."
            )
            result["what_worked"] = []
            result["what_underperformed"] = []
            result["learning_for_next_campaign"] = result[
                "recommended_actions"
            ]
            result["executive_summary"] = result["performance_insight"]
            result["interpretation"] = []
            result["combined_insight"] = ""
            result["combined_actions"] = []
            return result

        if strategy_context:
            payload["planned_strategy"] = strategy_context
        if intelligence:
            payload["deterministic_diagnosis"] = intelligence.get("diagnosis")
            payload["funnel"] = intelligence.get("funnel")
            payload["platform_comparison"] = intelligence.get("comparison")
        if customer_voice:
            payload["customer_voice_context"] = customer_voice
            payload["customer_voice_caution"] = (
                "Customer support data is company context only. "
                "Do not claim the campaign caused those conversations."
            )

        system_prompt = (
            "You are an AI marketing performance advisor. "
            "Use only the supplied metrics. Never invent numbers. "
            "Never calculate CTR, totals, or percentages. "
            "If a planned strategy is supplied, compare results to "
            "that plan qualitatively without inventing KPI targets. "
            "Use words such as may indicate, suggests, or appears "
            "when explaining causes. Return JSON only."
        )

        prompt = f"""
Analyze ONLY the campaign metrics supplied below.

Do not invent numbers or claim data that is not provided.
Do not change calculated metrics.
Return concise, actionable recommendations for a Marketing Specialist.
Arabic, if used, must be natural professional Arabic.

Identify:
1. overall performance insight / executive summary
2. strengths / what worked
3. weaknesses / what underperformed
4. likely interpretation (cautious)
5. 3–5 recommended actions
6. learning for the next campaign
7. optional combined insight if customer_voice_context is present

When metrics are missing or insufficient, explicitly say there is insufficient data.
Do not recommend unsupported changes as facts.
Do not invent expected KPI numbers.
Do not claim an objective was achieved unless a numeric target was supplied.
Planned strategy, if present, is context only.

Campaign metrics JSON:
{json.dumps(payload, ensure_ascii=False)}

Return JSON with this shape:
{{
  "performance_insight": "...",
  "executive_summary": "...",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "what_worked": ["..."],
  "what_underperformed": ["..."],
  "likely_interpretation": ["..."],
  "recommended_actions": ["...", "..."],
  "learning_for_next_campaign": ["..."],
  "combined_insight": "...",
  "combined_actions": ["..."]
}}
""".strip()

        raw = self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=900,
        )

        result = self._parse_response(raw)
        rating, basis = self._qualitative_rating(summary)
        result["overall_evaluation"] = rating
        result["evaluation_basis"] = basis
        return result
