from datetime import date
import re


def campaign_progress_percent(campaign):
    start = getattr(campaign, "start_date", None)
    end = getattr(campaign, "end_date", None)

    if not start or not end:
        return None

    try:
        total_days = (end - start).days
    except TypeError:
        return None

    today = date.today()

    if today < start:
        return 0

    if today >= end:
        return 100

    if total_days <= 0:
        return 100

    elapsed = (today - start).days
    percent = round((elapsed / total_days) * 100)
    return max(0, min(100, percent))


def parse_suggestion_display(content_text):
    text = str(content_text or "").strip()
    fields = {
        "title": "",
        "caption": "",
        "cta": "",
        "hashtags": "",
    }

    if not text:
        return {
            "parsed": False,
            "raw": "",
            **fields,
        }

    patterns = {
        "title": r"Title\s*:\s*(.*?)(?=\n\s*(?:Caption|CTA|Call to Action|Hashtags)\s*:|\Z)",
        "caption": r"Caption\s*:\s*(.*?)(?=\n\s*(?:CTA|Call to Action|Hashtags|Title)\s*:|\Z)",
        "cta": (
            r"(?:CTA|Call to Action)\s*:\s*(.*?)(?=\n\s*(?:Hashtags|Title|Caption)\s*:|\Z)"
        ),
        "hashtags": r"Hashtags\s*:\s*(.*?)(?=\n\s*(?:Title|Caption|CTA|Call to Action)\s*:|\Z)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            fields[key] = " ".join(match.group(1).split()).strip()

    parsed = any(fields.values())

    return {
        "parsed": parsed,
        "raw": text,
        **fields,
    }
