from ai_services.clients.cloudflare_ai_client import CloudflareAIClient
from ai_services.services.content_validator import ContentValidator
from ai_services.services.knowledge_service import KnowledgeService


class ContentGenerator:
    """
    Generates exactly 3 marketing suggestions using Cloudflare text AI.

    Supports an optional creative_brief dict so the generated copy
    stays aligned with the poster concept chosen by the user.

    Public method used by dashboard/views.py:
        generate_campaign_content(
            campaign=...,
            language="Arabic",
            creative_brief={...},
        )

    Return format:
        {
            "content": "...",
            "validation": {...}
        }
    """

    def __init__(self):
        self.ai_client = CloudflareAIClient()
        self.knowledge_service = KnowledgeService()
        self.validator = ContentValidator()

    def _get_knowledge_context(self, campaign):
        result = self.knowledge_service.get_company_context(
            campaign.company
        )

        if not result:
            return ""

        if isinstance(result, str):
            return result.strip()

        return str(result).strip()

    def _validate_content(self, content, campaign):
        validation_result = self.validator.validate(
            content,
            campaign,
        )

        if isinstance(validation_result, dict):
            if "is_valid" not in validation_result:
                if "valid" in validation_result:
                    validation_result["is_valid"] = bool(
                        validation_result["valid"]
                    )

                elif "passed" in validation_result:
                    validation_result["is_valid"] = bool(
                        validation_result["passed"]
                    )

            validation_result.setdefault(
                "errors",
                [],
            )

            return validation_result

        if isinstance(validation_result, bool):
            return {
                "is_valid": validation_result,
                "errors": (
                    []
                    if validation_result
                    else [
                        "Generated content did not pass validation."
                    ]
                ),
            }

        raise RuntimeError(
            "ContentValidator returned an unsupported result."
        )

    def generate_campaign_content(
        self,
        campaign,
        language="Arabic",
        creative_brief=None,
    ):
        creative_brief = creative_brief or {}

        company = campaign.company
        product = campaign.product

        company_name = getattr(
            company,
            "company_name",
            "",
        )

        company_industry = getattr(
            company,
            "industry",
            "",
        )

        company_description = (
            getattr(
                company,
                "description",
                "",
            )
            or ""
        )

        product_name = (
            getattr(
                product,
                "product_name",
                "",
            )
            if product
            else ""
        )

        product_description = (
            getattr(
                product,
                "description",
                "",
            )
            if product
            else ""
        ) or ""

        campaign_name = getattr(
            campaign,
            "campaign_name",
            "",
        )

        campaign_objective = (
            getattr(
                campaign,
                "objective",
                "",
            )
            or ""
        )

        platform = getattr(
            campaign,
            "platform",
            "",
        )

        knowledge_context = self._get_knowledge_context(
            campaign
        )

        brief_focus = str(
            creative_brief.get(
                "focus",
                "",
            )
        ).strip()

        brief_style = str(
            creative_brief.get(
                "style",
                "Premium Product Ad",
            )
        ).strip()

        brief_colors = str(
            creative_brief.get(
                "colors",
                "",
            )
        ).strip()

        brief_background = str(
            creative_brief.get(
                "background",
                "",
            )
        ).strip()

        brief_composition = str(
            creative_brief.get(
                "composition",
                "Product Centered",
            )
        ).strip()

        brief_mood = str(
            creative_brief.get(
                "mood",
                "",
            )
        ).strip()

        brief_additional = str(
            creative_brief.get(
                "additional",
                "",
            )
        ).strip()

        system_prompt = (
            "You are a professional marketing content strategist and copywriter. "
            "Follow the requested output structure exactly. "
            "Never invent discounts, prices, percentages, statistics, "
            "promo codes, certifications, partnerships, URLs, or "
            "product features that were not supplied."
        )

        prompt = f"""
Create exactly THREE different marketing content suggestions.

ROLE
Write as a professional marketing content strategist and copywriter.

LANGUAGE
{language}
If the language is Arabic, use natural professional Arabic. Do not produce awkward literal translations.

COMPANY
Name: {company_name}
Industry: {company_industry}
Description: {company_description or "Not provided"}

PRODUCT
Name: {product_name or "No specific product"}
Description: {product_description or "Not provided"}

CAMPAIGN
Name: {campaign_name}
Objective: {campaign_objective or "Not provided"}
Platform: {platform}

KNOWLEDGE BASE
Use this only as factual grounding. Never invent facts that are not present:
{knowledge_context or "No additional knowledge-base context was provided."}

CREATIVE BRIEF
Main advertising focus: {brief_focus or "Not specified"}
Visual style: {brief_style or "Premium Product Ad"}
Preferred color palette: {brief_colors or "No specific palette"}
Background or scene: {brief_background or "Not specified"}
Composition: {brief_composition or "Product Centered"}
Desired mood: {brief_mood or "Not specified"}
Additional direction: {brief_additional or "None"}

RULES
- Produce exactly 3 suggestions that are meaningfully different.
- Match the tone and format of {platform}.
- Write natural, publishable copy in {language}.
- Include a clear call to action when appropriate.
- Include relevant hashtags when appropriate.
- Avoid generic filler and unsupported claims.
- Never invent product or company facts that are not in the context above.
- Keep all three aligned with the creative brief.
- Do not add explanations before or after the suggestions.

RETURN EXACTLY THIS STRUCTURE:

Suggestion 1

Title:
...

Caption:
...

Hashtags:
...

Call to Action:
...

Suggestion 2

Title:
...

Caption:
...

Hashtags:
...

Call to Action:
...

Suggestion 3

Title:
...

Caption:
...

Hashtags:
...

Call to Action:
...
""".strip()

        generated_content = self.ai_client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=1600,
        )

        validation = self._validate_content(
            generated_content,
            campaign,
        )

        return {
            "content": generated_content,
            "validation": validation,
        }
