import os
import re
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

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
        self.image_client = None

    def _get_image_client(self):
        if not (
            os.getenv("CLOUDFLARE_ACCOUNT_ID")
            and os.getenv("CLOUDFLARE_API_TOKEN")
        ):
            raise RuntimeError(
                "Cloudflare image generation is not configured."
            )
        if self.image_client is None:
            self.image_client = CloudflareImageClient()
        return self.image_client

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

    @staticmethod
    def _is_reference_image_error(
        exc
    ):
        message = str(exc).lower()

        return (
            "input_image" in message
            or "reference image" in message
            or "image input" in message
            or (
                "unsupported" in message
                and "image" in message
            )
            or (
                "512" in message
                and "image" in message
            )
            or "invalid image" in message
            or "could not process the image" in message
        )

    @staticmethod
    def _load_product_reference_image(
        campaign_content
    ):
        product = getattr(
            campaign_content.campaign,
            "product",
            None,
        )

        image_field = getattr(
            product,
            "product_image",
            None,
        ) if product else None

        if not image_field or not getattr(image_field, "name", None):
            return None

        try:
            image_field.open("rb")
            image_bytes = image_field.read()
        except Exception:
            return None
        finally:
            try:
                image_field.close()
            except Exception:
                pass

        if not image_bytes:
            return None

        try:
            image = Image.open(
                BytesIO(image_bytes)
            )
            image = image.convert("RGB")
            # FLUX.2 Klein requires reference images smaller than 512x512.
            image.thumbnail(
                (511, 511)
            )
            buffer = BytesIO()
            image.save(
                buffer,
                format="PNG"
            )
            prepared_bytes = buffer.getvalue()
            filename = "input_image_0.png"
        except Exception:
            prepared_bytes = image_bytes
            original_name = os.path.basename(
                getattr(image_field, "name", "") or ""
            )
            filename = (
                original_name
                if original_name.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp")
                )
                else "input_image_0.png"
            )

        return {
            "bytes": prepared_bytes,
            "filename": filename,
            "content_type": "image/png",
        }

    def _generate_image(
        self,
        prompt,
        reference_image=None,
    ):
        kwargs = {
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
        }

        if reference_image:
            kwargs["reference_image"] = (
                reference_image["bytes"]
            )
            kwargs["reference_filename"] = (
                reference_image["filename"]
            )
            kwargs["reference_content_type"] = (
                reference_image["content_type"]
            )

        try:
            return self._get_image_client().generate_image(
                **kwargs
            )

        except RuntimeError as exc:
            if (
                reference_image
                and self._is_reference_image_error(
                    exc
                )
            ):
                return self._get_image_client().generate_image(
                    prompt=prompt,
                    width=1024,
                    height=1024,
                )

            raise

    @staticmethod
    def _resample_filter():
        resampling = getattr(Image, "Resampling", None)
        if resampling is not None:
            return resampling.LANCZOS
        return getattr(Image, "LANCZOS", Image.BICUBIC)

    @staticmethod
    def _load_font(size):
        candidates = [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _compose_local_poster(
        self,
        campaign_content,
        reference_image=None,
        fields=None,
    ):
        size = 1024
        poster = Image.new("RGB", (size, size), (23, 32, 51))
        draw = ImageDraw.Draw(poster)
        draw.rectangle((0, 0, size, 36), fill=(47, 111, 102))
        draw.rectangle((0, size - 120, size, size), fill=(16, 22, 34))

        fields = fields or self._extract_fields(
            campaign_content.content_text
        )
        campaign = campaign_content.campaign
        product = getattr(campaign, "product", None)
        headline = (
            self._clean(fields.get("title"))
            or self._clean(campaign_content.title)
            or self._clean(getattr(campaign, "campaign_name", ""))
            or "Campaign poster"
        )
        supporting = (
            self._clean(fields.get("cta"))
            or self._clean(getattr(product, "product_name", "") if product else "")
            or self._clean(getattr(campaign.company, "company_name", ""))
        )

        product_image = None
        if reference_image and reference_image.get("bytes"):
            try:
                product_image = Image.open(
                    BytesIO(reference_image["bytes"])
                ).convert("RGB")
            except Exception:
                product_image = None

        if product_image is None:
            image_field = getattr(product, "product_image", None) if product else None
            if image_field and getattr(image_field, "name", None):
                try:
                    image_field.open("rb")
                    product_image = Image.open(image_field).convert("RGB")
                except Exception:
                    product_image = None
                finally:
                    try:
                        image_field.close()
                    except Exception:
                        pass

        if product_image is not None:
            product_image.thumbnail((720, 560), self._resample_filter())
            offset = (
                (size - product_image.width) // 2,
                120 + (560 - product_image.height) // 2,
            )
            poster.paste(product_image, offset)
        else:
            draw.rounded_rectangle(
                (180, 160, 844, 680),
                radius=28,
                outline=(47, 111, 102),
                width=4,
            )

        title_font = self._load_font(42)
        support_font = self._load_font(24)
        draw.text(
            (64, size - 96),
            headline[:48],
            fill=(255, 255, 255),
            font=title_font,
        )
        if supporting:
            draw.text(
                (64, size - 50),
                supporting[:52],
                fill=(184, 196, 212),
                font=support_font,
            )

        buffer = BytesIO()
        poster.save(buffer, format="PNG")
        return buffer.getvalue()

    def _build_primary_prompt(
        self,
        campaign_content,
        creative_brief,
        fields,
        has_product_reference=False,
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

        product_reference_instructions = ""

        if has_product_reference:
            product_reference_instructions = """
PRODUCT REFERENCE IMAGE
A product photo is provided as input_image_0.
Preserve the visual identity and recognizable appearance of the referenced product.
Use this exact product as the hero subject of the advertisement.
Do not invent a different product, substitute a similar item, or change the product's distinctive look.
"""

        return f"""
Create one finished, professional square social-media advertisement.

This must look like a real commercial POSTER, not a plain product photo.

BRAND
Company: {company_name}
Industry: {industry}

PRODUCT
Product name: {product_name or "Commercial product"}
Product description: {product_description or "Not provided"}
{product_reference_instructions}
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
        has_product_reference=False,
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

{"Use the provided product photo as input_image_0. Preserve the visual identity of that product and do not invent a different product." if has_product_reference else ""}

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

        reference_image = (
            self._load_product_reference_image(
                campaign_content
            )
        )

        has_product_reference = bool(
            reference_image
        )

        primary_prompt = (
            self._build_primary_prompt(
                campaign_content,
                creative_brief,
                fields,
                has_product_reference=has_product_reference,
            )
        )

        try:
            image_bytes = self._generate_image(
                primary_prompt,
                reference_image=reference_image,
            )

        except RuntimeError as exc:

            if self._is_cloudflare_flagged_error(exc):
                safe_prompt = (
                    self._build_safe_retry_prompt(
                        campaign_content,
                        creative_brief,
                        has_product_reference=has_product_reference,
                    )
                )
                try:
                    image_bytes = self._generate_image(
                        safe_prompt,
                        reference_image=reference_image,
                    )
                except Exception:
                    image_bytes = self._compose_local_poster(
                        campaign_content,
                        reference_image=reference_image,
                        fields=fields,
                    )
            else:
                image_bytes = self._compose_local_poster(
                    campaign_content,
                    reference_image=reference_image,
                    fields=fields,
                )

        except Exception:
            image_bytes = self._compose_local_poster(
                campaign_content,
                reference_image=reference_image,
                fields=fields,
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
