import json
import re

from ai_services.clients.cloudflare_ai_client import CloudflareAIClient


class StrategyGenerationError(ValueError):
    """Raised when the model response cannot be turned into a strategy."""


class MarketingStrategyAgent:
    """Proposes a structured campaign strategy. Does not create campaigns."""

    def __init__(self, llm=None):
        self.llm = llm or CloudflareAIClient()

    def generate(self, inputs):
        inputs = inputs or {}
        system_prompt = (
            "You are a professional AI marketing strategist. "
            "Design a practical campaign strategy based ONLY on the "
            "supplied business information. Do not invent facts about "
            "the company or product. Return JSON only."
        )
        prompt = self._build_prompt(inputs)
        raw = self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
            max_tokens=1400,
        )
        return self.parse_response(raw)

    def parse_response(self, raw_text):
        text = str(raw_text or "").strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE)
            text = re.sub(r"```$", "", text).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1 or end <= start:
            raise StrategyGenerationError(
                "The strategy response was not valid JSON."
            )

        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise StrategyGenerationError(
                "The strategy response could not be parsed as JSON."
            ) from exc

        if not isinstance(data, dict):
            raise StrategyGenerationError(
                "The strategy response was not a JSON object."
            )

        strategy = {
            "campaign_objective": _text(data.get("campaign_objective")),
            "target_audience": _text(data.get("target_audience")),
            "recommended_platform": _text(data.get("recommended_platform")),
            "strategy_summary": _text(data.get("strategy_summary")),
            "content_strategy": _as_list(data.get("content_strategy")),
            "creative_direction": _text(data.get("creative_direction")),
            "budget_strategy": _text(data.get("budget_strategy")),
            "recommended_kpis": _as_list(data.get("recommended_kpis")),
            "messaging_angle": _text(data.get("messaging_angle")),
            "call_to_action_strategy": _text(
                data.get("call_to_action_strategy")
            ),
            "reasoning": _text(data.get("reasoning")),
        }

        required = (
            "campaign_objective",
            "strategy_summary",
            "recommended_platform",
        )
        missing = [key for key in required if not strategy[key]]
        if missing:
            raise StrategyGenerationError(
                "The strategy response was missing required sections."
            )

        return strategy

    def _build_prompt(self, inputs):
        preferred = _text(inputs.get("preferred_platform")) or "Not specified"
        additional = _text(inputs.get("additional_information")) or "None"

        return f"""
You are a professional AI marketing strategist.

Your task is to design a practical campaign strategy based ONLY on the supplied business information.

Do not invent facts about the company or product.

Inputs:

Company:
{_text(inputs.get("company_information")) or "Not provided"}

Product:
{_text(inputs.get("product_information")) or "Not provided"}

Marketing goal:
{_text(inputs.get("marketing_goal")) or "Not provided"}

Target audience:
{_text(inputs.get("target_audience")) or "Not provided"}

Budget:
{_text(inputs.get("budget")) or "Not provided"}

Campaign dates/duration:
{_text(inputs.get("dates")) or "Not provided"}

Preferred platform:
{preferred}

Additional instructions:
{additional}

Return a practical strategy for a Marketing Manager.

The strategy must include:

1. Campaign Objective
2. Target Audience
3. Recommended Platform
4. Strategy Summary
5. Content Strategy
6. Creative Direction
7. Budget Strategy
8. Recommended KPIs
9. Messaging Angle
10. CTA Strategy
11. Short explanation of why the strategy is appropriate

Rules:
- Do not invent unsupported company/product facts.
- Keep recommendations realistic for the provided budget.
- If the user supplied a preferred platform, respect it unless there is a strong reason not to; explain any alternative.
- Keep recommendations actionable.
- Do not claim guaranteed performance.
- Do not invent performance statistics.
- Respond in the same language as the Marketing Specialist input when practical.
- For Arabic, use natural professional Arabic.

Return JSON only with this exact shape:
{{
  "campaign_objective": "...",
  "target_audience": "...",
  "recommended_platform": "...",
  "strategy_summary": "...",
  "content_strategy": ["...", "...", "..."],
  "creative_direction": "...",
  "budget_strategy": "...",
  "recommended_kpis": ["...", "...", "..."],
  "messaging_angle": "...",
  "call_to_action_strategy": "...",
  "reasoning": "..."
}}
""".strip()


def _text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n".join(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    return str(value).strip()


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
    text = str(value).strip()
    if not text:
        return []
    parts = [
        part.strip(" -*\t")
        for part in re.split(r"[\n;]+", text)
        if part.strip(" -*\t")
    ]
    return parts or [text]
