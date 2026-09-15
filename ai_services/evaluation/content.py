import re

from django.apps import apps

from ai_services.evaluation.grader import (
    CONTENT_GRADER_SYSTEM,
    GradingUnavailable,
    content_grader_prompt,
    grade_with_llm,
)
from ai_services.evaluation.io import json_ready
from ai_services.evaluation.metrics import (
    clamp_five,
    content_quality_from_scores,
    content_summary,
)
from ai_services.services.content_generator import ContentGenerator


CRITERIA = (
    "campaign_relevance",
    "factual_consistency",
    "platform_appropriateness",
    "language_quality",
    "cta_quality",
)


def split_suggestions(content_text):
    sections = re.split(
        r"(?=Suggestion\s+\d+\s*)",
        str(content_text or ""),
        flags=re.IGNORECASE,
    )
    return [
        section.strip()
        for section in sections
        if section.strip()
        and re.match(r"Suggestion\s+\d+", section.strip(), flags=re.IGNORECASE)
    ]


def _load_campaign(case):
    campaign_id = case.get("campaign_id")
    if campaign_id in (None, "", "REPLACE_WITH_CAMPAIGN_ID"):
        return None
    Campaign = apps.get_model("campaign", "Campaign")
    return Campaign.objects.select_related("company", "product").get(
        id=int(campaign_id)
    )


def _case_from_campaign(case, campaign):
    company = campaign.company
    product = campaign.product
    merged = dict(case)
    merged.setdefault("company", getattr(company, "company_name", ""))
    merged.setdefault(
        "product",
        getattr(product, "product_name", "") if product else "",
    )
    merged.setdefault("campaign_objective", campaign.objective)
    merged.setdefault("platform", campaign.platform)
    return merged


def _scores_from_grade(graded):
    scores = {}
    reasons = {}
    for key in CRITERIA:
        block = graded.get(key) if isinstance(graded, dict) else None
        if not isinstance(block, dict):
            scores[key] = None
            reasons[key] = None
            continue
        scores[key] = clamp_five(block.get("score"))
        reasons[key] = str(block.get("reason") or "").strip() or None
    return scores, reasons


def evaluate_content_case(case, generator, grader_llm=None):
    base = {
        "id": case.get("id"),
        "campaign_id": case.get("campaign_id"),
        "status": "failed",
        "error": None,
        "raw_content": None,
        "validation": None,
        "suggestions": [],
        "human_scores": None,
    }
    try:
        campaign = _load_campaign(case)
    except Exception as exc:
        base["error"] = str(exc)
        return [base]
    if campaign is None:
        base["status"] = "skipped"
        base["error"] = (
            "Set campaign_id to a real Campaign primary key before running."
        )
        return [base]

    language = case.get("language") or "Arabic"
    creative_brief = case.get("creative_brief") or {}
    try:
        result = generator.generate_campaign_content(
            campaign=campaign,
            language=language,
            creative_brief=creative_brief,
        )
    except Exception as exc:
        base["error"] = str(exc)
        return [base]

    content_text = (result or {}).get("content") or ""
    base["raw_content"] = content_text
    base["validation"] = (result or {}).get("validation")
    suggestions = split_suggestions(content_text)
    if not suggestions:
        suggestions = [content_text] if content_text.strip() else []
    if not suggestions:
        base["error"] = "Generator returned empty content."
        return [base]

    graded_case = _case_from_campaign(case, campaign)
    records = []
    for index, suggestion in enumerate(suggestions, start=1):
        record = {
            "id": f"{case.get('id') or 'content'}_suggestion_{index}",
            "case_id": case.get("id"),
            "campaign_id": campaign.id,
            "suggestion_index": index,
            "generated_content": suggestion,
            "status": "evaluated",
            "error": None,
            "grading_error": None,
            "campaign_relevance": None,
            "factual_consistency": None,
            "platform_appropriateness": None,
            "language_quality": None,
            "cta_quality": None,
            "criterion_reasons": {},
            "total_score": None,
            "quality_percentage": None,
            "human_scores": None,
        }
        if grader_llm is None:
            record["grading_error"] = "LLM grader was not available."
            records.append(record)
            continue
        try:
            graded = grade_with_llm(
                grader_llm,
                content_grader_prompt(graded_case, suggestion),
                CONTENT_GRADER_SYSTEM,
            )
            scores, reasons = _scores_from_grade(graded)
            record["criterion_reasons"] = reasons
            quality = content_quality_from_scores(scores)
            if quality is None:
                record["grading_error"] = (
                    "Grader JSON was missing one or more criterion scores."
                )
            else:
                record.update(quality)
        except GradingUnavailable as exc:
            record["grading_error"] = str(exc)
        except Exception as exc:
            record["grading_error"] = str(exc)
        records.append(record)
    return records


def run_content_evaluation(cases, generator=None, grader_llm=None):
    generator = generator or ContentGenerator()
    records = []
    for case in cases:
        records.extend(
            json_ready(item)
            for item in evaluate_content_case(
                case,
                generator,
                grader_llm=grader_llm,
            )
        )
    return records, content_summary(records)
