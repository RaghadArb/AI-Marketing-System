from campaign.models import PLATFORM_CHOICES


DRAFT_SESSION_KEY = "marketing_strategy_draft"
CAMPAIGN_SESSION_KEY = "campaign_strategy_by_id"
BRIEF_SESSION_KEY = "studio_creative_brief_by_campaign"
LAST_CAMPAIGN_KEY = "studio_last_campaign_id"

STRATEGY_TEXT_FIELDS = (
    "campaign_objective",
    "target_audience",
    "recommended_platform",
    "strategy_summary",
    "creative_direction",
    "budget_strategy",
    "messaging_angle",
    "call_to_action_strategy",
    "reasoning",
)

UNMAPPED_CAMPAIGN_FIELDS = (
    "target_audience",
    "content_strategy",
    "creative_direction",
    "budget_strategy",
    "recommended_kpis",
    "messaging_angle",
    "call_to_action_strategy",
    "reasoning",
)


def strategy_from_post(post):
    def lines(name):
        raw = post.get(name, "")
        return [
            part.strip()
            for part in str(raw).splitlines()
            if part.strip()
        ]

    strategy = {
        field: str(post.get(field, "")).strip()
        for field in STRATEGY_TEXT_FIELDS
    }
    strategy["content_strategy"] = lines("content_strategy")
    strategy["recommended_kpis"] = lines("recommended_kpis")
    return strategy


def company_brief(company):
    if company is None:
        return ""
    parts = [
        f"Name: {company.company_name}",
        f"Industry: {company.industry or 'Not provided'}",
    ]
    if company.description:
        parts.append(f"Description: {company.description}")
    if company.website:
        parts.append(f"Website: {company.website}")
    return "\n".join(parts)


def product_brief(product):
    if product is None:
        return "No specific product"
    parts = [
        f"Name: {product.product_name}",
        f"Category: {product.category or 'Not provided'}",
        f"Price: {product.price}",
        f"Status: {product.status}",
    ]
    if product.description:
        parts.append(f"Description: {product.description}")
    return "\n".join(parts)


def map_platform(recommended):
    text = str(recommended or "").strip()
    if not text:
        return "Other"

    lowered = text.lower()
    for value, _label in PLATFORM_CHOICES:
        if value.lower() == lowered or value.lower() in lowered:
            return value

    aliases = {
        "ig": "Instagram",
        "insta": "Instagram",
        "reels": "Instagram",
        "fb": "Facebook",
        "meta": "Instagram",
        "tt": "TikTok",
        "tik tok": "TikTok",
        "li": "LinkedIn",
        "adwords": "Google Ads",
        "search ads": "Google Ads",
        "newsletter": "Email",
        "e-mail": "Email",
    }
    for needle, platform in aliases.items():
        if needle in lowered:
            return platform

    return "Other"


def campaign_name_from_strategy(strategy, product=None):
    objective = str(strategy.get("campaign_objective") or "").strip()
    if objective:
        return objective[:150]
    if product is not None:
        return f"{product.product_name} campaign"[:150]
    return "AI marketing strategy"


def brief_from_strategy(strategy):
    strategy = strategy or {}
    content_lines = strategy.get("content_strategy") or []
    if isinstance(content_lines, str):
        content_lines = [
            line.strip()
            for line in content_lines.splitlines()
            if line.strip()
        ]

    additional_parts = []
    if strategy.get("target_audience"):
        additional_parts.append(
            "Target audience: " + strategy["target_audience"]
        )
    if content_lines:
        additional_parts.append(
            "Content strategy:\n- " + "\n- ".join(content_lines)
        )
    if strategy.get("call_to_action_strategy"):
        additional_parts.append(
            "CTA strategy: " + strategy["call_to_action_strategy"]
        )
    if strategy.get("budget_strategy"):
        additional_parts.append(
            "Budget strategy: " + strategy["budget_strategy"]
        )

    return {
        "focus": (
            strategy.get("messaging_angle")
            or strategy.get("campaign_objective")
            or ""
        ).strip(),
        "style": "Premium Product Ad",
        "colors": "",
        "background": "",
        "composition": "Product Centered",
        "mood": str(strategy.get("creative_direction") or "").strip(),
        "additional": "\n\n".join(additional_parts),
    }


def save_draft(request, payload):
    request.session[DRAFT_SESSION_KEY] = payload
    request.session.modified = True


def load_draft(request):
    return request.session.get(DRAFT_SESSION_KEY) or None


def save_campaign_strategy(request, campaign_id, payload):
    stored = request.session.get(CAMPAIGN_SESSION_KEY) or {}
    stored[str(campaign_id)] = payload
    if len(stored) > 30:
        extra = list(stored.keys())[:-30]
        for key in extra:
            stored.pop(key, None)
    request.session[CAMPAIGN_SESSION_KEY] = stored
    request.session.modified = True


def load_campaign_strategy(request, campaign_id):
    stored = request.session.get(CAMPAIGN_SESSION_KEY) or {}
    return stored.get(str(campaign_id))


def save_creative_brief(request, campaign_id, brief):
    if not campaign_id:
        return
    stored = request.session.get(BRIEF_SESSION_KEY) or {}
    stored[str(campaign_id)] = brief
    request.session[BRIEF_SESSION_KEY] = stored
    request.session[LAST_CAMPAIGN_KEY] = int(campaign_id)
    request.session.modified = True


def load_creative_brief(request, campaign_id):
    stored = request.session.get(BRIEF_SESSION_KEY) or {}
    return stored.get(str(campaign_id))


def remember_workflow_campaign(request, campaign_id):
    if not campaign_id:
        return
    request.session[LAST_CAMPAIGN_KEY] = int(campaign_id)
    request.session.modified = True


def workflow_campaign_id(request, fallback=None):
    if fallback:
        return int(fallback)
    raw = request.session.get(LAST_CAMPAIGN_KEY)
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def strategy_context_for_advisor(strategy):
    if not strategy:
        return None
    context = {}
    for key in (
        "campaign_objective",
        "target_audience",
        "recommended_platform",
        "messaging_angle",
        "call_to_action_strategy",
    ):
        value = strategy.get(key)
        if value:
            context[key] = value
    kpis = strategy.get("recommended_kpis") or []
    if kpis:
        context["planned_kpi_themes"] = kpis
        context["note"] = (
            "Planned KPI themes are directional only. "
            "Do not treat them as numeric targets unless those "
            "numbers appear in recorded metrics."
        )
    return context or None
