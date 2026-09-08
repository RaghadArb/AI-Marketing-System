import re

from django.core.files.base import ContentFile

from ai_services.clients.cloudflare_image_client import (
    CloudflareImageClient,
)


class PosterGenerator:
    """
    Generates a professional poster from:
    - campaign/company/product data
    - the chosen AI text suggestion
    - the marketing specialist's creative brief

    If Cloudflare returns safety error 3030, one simplified retry
    is attempted automatically.
    """

    def __init__(self):
        self.image_client = CloudflareImageClient()

    @staticmethod
    def _clean(value):
        if value is None:
            return ""

        return " ".join(
            str(value)
            .replace("\x00", " ")
            .split()
        ).strip()

    @classmethod
    def _extract_fields(
        cls,
        content_text
    ):
        fields = {
            "title": "",
            "caption": "",
            "hashtags": "",
            "cta": "",
        }

        text = content_text or ""

        patterns = {
            "title": (
                r"Title\s*:\s*(.*?)"
                r"(?=\n\s*(?:Caption|Hashtags|Call to Action)\s*:|\Z)"
            ),
            "caption": (
                r"Caption\s*:\s*(.*?)"
                r"(?=\n\s*(?:Hashtags|Call to Action)\s*:|\Z)"
            ),
            "hashtags": (
                r"Hashtags\s*:\s*(.*?)"
                r"(?=\n\s*Call to Action\s*:|\Z)"
            ),
            "cta": (
                r"Call to Action\s*:\s*(.*?)"
                r"(?=\Z)"
            ),
        }

        for key, pattern in patterns.items():
            match = re.search(
                pattern,
                text,
                flags=(
                    re.IGNORECASE
                    | re.DOTALL
                ),
            )

            if match:
                fields[key] = cls._clean(
                    match.group(1)
                )

        return fields

    @staticmethod
    def _is_cloudflare_flagged_error(
        exc
    ):
        message = str(exc).lower()

        return (
            "3030" in message
            or "output has been flagged" in message
            or "choose another prompt" in message
        )

    def _build_primary_prompt(
        self,
        campaign_content,
        creative_brief,
        fields,
    ):
        campaign = campaign_content.campaign
        company = campaign.company
        product = campaign.product

        company_name = self._clean(
            getattr(
                company,
                "company_name",
                "",
            )
        )

        industry = self._clean(
            getattr(
                company,
                "industry",
                "",
            )
        )

        product_name = (
            self._clean(
                getattr(
                    product,
                    "product_name",
                    "",
                )
            )
            if product
            else ""
        )

        product_description = (
            self._clean(
                getattr(
                    product,
                    "description",
                    "",
                )
            )
            if product
            else ""
        )

        title = (
            fields["title"]
            or self._clean(
                campaign_content.title
            )
        )

        caption = fields["caption"]
        cta = fields["cta"]

        focus = self._clean(
            creative_brief.get(
                "focus",
                ""
            )
        )

        style = self._clean(
            creative_brief.get(
                "style",
                "Premium Product Ad"
            )
        )

        colors = self._clean(
            creative_brief.get(
                "colors",
                ""
            )
        )

        background = self._clean(
            creative_brief.get(
                "background",
                ""
            )
        )

        composition = self._clean(
            creative_brief.get(
                "composition",
                "Product Centered"
            )
        )

        mood = self._clean(
            creative_brief.get(
                "mood",
                ""
            )
        )

        additional = self._clean(
            creative_brief.get(
                "additional",
                ""
            )
        )

        return f"""
Create one finished, professional square social-media advertisement.

This must look like a real commercial POSTER, not a plain product photo.

BRAND
Company: {company_name}
Industry: {industry}

PRODUCT
Product name: {product_name or "Commercial product"}
Product description: {product_description or "Not provided"}

CAMPAIGN
Campaign: {campaign.campaign_name}
Objective: {campaign.objective}
Platform: {campaign.platform}

MARKETING SPECIALIST CREATIVE BRIEF
Main advertising focus:
{focus}

Visual style:
{style}

Preferred color palette:
{colors or "Choose colors that professionally fit the product and brand"}

Background or scene:
{background or "Professional clean advertising environment"}

Composition:
{composition}

Mood:
{mood or "Professional and commercially attractive"}

Additional creative instructions:
{additional or "None"}

SUGGESTION MESSAGE
Use this caption only to understand the advertising message:
{caption or title}

POSTER COPY
Headline:
{title}

Call to action:
{cta}

DESIGN REQUIREMENTS
- The product must be the hero of the advertisement.
- Show the product prominently and clearly.
- Create a complete designed advertisement with layout,
  hierarchy, background, spacing, and commercial styling.
- Follow the marketing specialist's creative brief closely.
- Use professional product-advertising photography.
- Use premium lighting and realistic shadows.
- Create intentional negative space for typography.
- Match the requested composition.
- Match the requested color palette when provided.
- Match the requested background or scene when provided.
- Keep the visual polished, modern, and suitable for Instagram.
- Avoid a generic stock-photo appearance.
- Avoid a plain isolated product-only image.
- Avoid collage aesthetics unless explicitly requested.
- Do not invent prices, discounts, promo codes, URLs,
  statistics, certifications, or social handles.
- Do not show hashtags.
- Do not show prompt labels or instructions.
- Keep visible marketing text minimal.
""".strip()

    def _build_safe_retry_prompt(
        self,
        campaign_content,
        creative_brief,
    ):
        campaign = campaign_content.campaign
        product = campaign.product

        product_name = (
            self._clean(
                getattr(
                    product,
                    "product_name",
                    "",
                )
            )
            if product
            else "commercial product"
        )

        focus = self._clean(
            creative_brief.get(
                "focus",
                ""
            )
        )

        style = self._clean(
            creative_brief.get(
                "style",
                "Premium Product Ad"
            )
        )

        colors = self._clean(
            creative_brief.get(
                "colors",
                ""
            )
        )

        background = self._clean(
            creative_brief.get(
                "background",
                ""
            )
        )

        composition = self._clean(
            creative_brief.get(
                "composition",
                "Product Centered"
            )
        )

        return f"""
Create a clean square commercial product advertisement.

Featured product:
{product_name}

Main visual:
{focus or "Feature the product prominently"}

Style:
{style}

Colors:
{colors or "Professional brand-appropriate colors"}

Background:
{background or "Clean advertising background"}

Composition:
{composition}

Make the product the clear central hero.
Use professional studio-style product photography,
premium lighting, realistic shadows, elegant spacing,
and a finished modern advertisement layout.

No people.
No text.
No logos.
No prices.
No discounts.
No watermarks.
""".strip()

    def generate_for_content(
        self,
        campaign_content,
        creative_brief=None,
    ):
        creative_brief = (
            creative_brief
            or {}
        )

        fields = self._extract_fields(
            campaign_content.content_text
        )

        primary_prompt = (
            self._build_primary_prompt(
                campaign_content,
                creative_brief,
                fields,
            )
        )

        try:
            image_bytes = (
                self.image_client
                .generate_image(
                    prompt=primary_prompt,
                    width=1024,
                    height=1024,
                )
            )

        except RuntimeError as exc:

            if not self._is_cloudflare_flagged_error(
                exc
            ):
                raise

            safe_prompt = (
                self._build_safe_retry_prompt(
                    campaign_content,
                    creative_brief,
                )
            )

            image_bytes = (
                self.image_client
                .generate_image(
                    prompt=safe_prompt,
                    width=1024,
                    height=1024,
                )
            )

        campaign = (
            campaign_content.campaign
        )

        filename = (
            f"campaign_{campaign.id}_"
            f"content_{campaign_content.id}.png"
        )

        campaign_content.poster.save(
            filename,
            ContentFile(
                image_bytes
            ),
            save=True,
        )

        return campaign_content.poster
