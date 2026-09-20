import logging
import os
import re
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

from ai_services.clients.cloudflare_image_client import (
    CloudflareImageClient,
)
from ai_services.clients.openrouter_image_client import (
    OpenRouterImageClient,
    OpenRouterImageGenerationError,
)

logger = logging.getLogger("ai_services.poster_generator")

POSTER_MODERATION_USER_MESSAGE = (
    "Poster generation was rejected by the image provider for this "
    "prompt or reference image. Try changing the creative brief or "
    "generating without the product reference image."
)


class PosterModerationRejected(RuntimeError):
    """Cloudflare error 3030 after the allowed moderation retry."""


class PosterProviderFallbackError(RuntimeError):
    """Both the primary image provider and Cloudflare fallback failed."""

    def __init__(self, primary_error, fallback_error):
        self.primary_error = primary_error
        self.fallback_error = fallback_error
        super().__init__(
            "OpenRouter image generation failed: "
            f"{primary_error}. Cloudflare fallback failed: {fallback_error}"
        )


class PosterGenerator:
    """
    Generates a professional poster from:
    - campaign/company/product data
    - the chosen AI text suggestion
    - the marketing specialist's creative brief

    Image generation uses OpenRouter first and Cloudflare FLUX as fallback.
    Failures raise; this class never returns a local/static poster.
    """

    def __init__(self):
        self.image_client = None
        self.openrouter_image_client = None
        self.image_provider = (
            os.getenv("POSTER_IMAGE_PROVIDER", "openrouter")
            .strip()
            .lower()
            or "openrouter"
        )

    def _get_openrouter_image_client(self):
        if self.openrouter_image_client is None:
            self.openrouter_image_client = OpenRouterImageClient()
        return self.openrouter_image_client

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

    @classmethod
    def _sanitize_for_image_model(cls, value):
        text = cls._clean(value)
        if not text:
            return ""
        text = re.sub(
            r"\b\d+\s*%\s*(off|discount|خصم)?\b",
            "seasonal offer",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(discount|sale|promo(?:tion)?|coupon|% off)\b",
            "offer",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"[$€£]\s?\d+(?:[.,]\d+)?", "offer", text)
        return cls._clean(text)

    @staticmethod
    def _cloudflare_http_status(exc):
        match = re.search(r"HTTP\s+(\d+)", str(exc), flags=re.IGNORECASE)
        if not match:
            return None
        return int(match.group(1))

    @staticmethod
    def _cloudflare_error_code(exc):
        match = re.search(
            r"['\"]code['\"]\s*:\s*(\d+)",
            str(exc),
        )
        if match:
            return int(match.group(1))
        return None

    @classmethod
    def _is_cloudflare_flagged_error(cls, exc):
        http_status = cls._cloudflare_http_status(exc)
        if http_status in (401, 403, 408, 429, 500, 502, 503, 504):
            return False
        if http_status is not None and http_status != 400:
            return False
        code = cls._cloudflare_error_code(exc)
        if code == 3030:
            return True
        message = str(exc).lower()
        return (
            "output has been flagged" in message
            and "choose another prompt" in message
        )

    @classmethod
    def _is_reference_image_error(cls, exc):
        if cls._is_cloudflare_flagged_error(exc):
            return False
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

    def _generate_cloudflare_image(
        self,
        prompt,
        reference_image=None,
        seed=None,
    ):
        kwargs = {
            "prompt": prompt,
            "width": 1024,
            "height": 1024,
        }
        if seed is not None:
            kwargs["seed"] = seed

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

    def _generate_image(
        self,
        prompt,
        reference_image=None,
        seed=None,
    ):
        if self.image_provider not in ("openrouter", "cloudflare"):
            raise RuntimeError(
                "POSTER_IMAGE_PROVIDER must be 'openrouter' or 'cloudflare'."
            )

        if self.image_provider == "cloudflare":
            return self._generate_cloudflare_image(
                prompt,
                reference_image=reference_image,
                seed=seed,
            )

        try:
            image_bytes = self._get_openrouter_image_client().generate_image(
                prompt=prompt,
                size="1024x1024",
            )
            if not self._valid_image_bytes(image_bytes):
                raise OpenRouterImageGenerationError(
                    "OpenRouter returned invalid image bytes."
                )
            return image_bytes
        except OpenRouterImageGenerationError as primary_error:
            logger.warning(
                "OpenRouter poster generation failed; using Cloudflare fallback. "
                "Error: %s",
                primary_error,
                exc_info=True,
            )
            try:
                return self._generate_cloudflare_image(
                    prompt,
                    reference_image=reference_image,
                    seed=seed,
                )
            except Exception as fallback_error:
                raise PosterProviderFallbackError(
                    primary_error,
                    fallback_error,
                ) from fallback_error

    def _build_primary_prompt(
        self,
        campaign_content,
        creative_brief,
        fields,
        has_product_reference=False,
        variation_index=1,
    ):
        campaign = campaign_content.campaign
        company = campaign.company
        product = campaign.product
        creative_brief = creative_brief or {}

        company_name = self._clean(getattr(company, "company_name", ""))
        industry = self._clean(getattr(company, "industry", ""))
        product_name = (
            self._clean(getattr(product, "product_name", ""))
            if product
            else ""
        )
        product_description = (
            self._clean(getattr(product, "description", ""))
            if product
            else ""
        )
        focus = self._clean(creative_brief.get("focus", ""))
        style = self._clean(creative_brief.get("style", ""))
        colors = self._clean(creative_brief.get("colors", ""))
        background = self._clean(creative_brief.get("background", ""))
        composition = self._clean(creative_brief.get("composition", ""))
        mood = self._clean(creative_brief.get("mood", ""))
        additional = self._clean(creative_brief.get("additional", ""))

        def line(label, value):
            value = self._clean(value)
            if not value:
                return ""
            return f"{label}: {value}\n"

        brief_block = "".join(
            [
                line("Main advertising focus / imagery", focus),
                line("Visual style", style),
                line("Colors", colors),
                line("Background", background),
                line("Composition / layout", composition),
                line("Mood / tone", mood),
                line("Extra user instructions", additional),
            ]
        ).strip() or "No additional creative brief was provided."

        angle = (
            "Use a slightly different camera angle than other variations, "
            "but keep every requested brief detail."
            if variation_index > 1
            else "Follow the requested composition exactly."
        )

        product_subject = product_name or "the advertised commercial product"
        campaign_name = self._clean(getattr(campaign, "campaign_name", ""))

        return f"""
Create one square commercial advertising photograph for social media.

Generate the IMAGE described by the marketing specialist's creative brief.
Do not ignore or replace those instructions with a generic template.

VISUAL SUBJECT
Depict this product as a physical object in the scene: {product_subject}
{line("What the product looks like", product_description).strip()}
{line("Industry context", industry).strip()}
Company, brand, and campaign names are private metadata only.
Do not print, engrave, or overlay any of these strings: {company_name or "n/a"}, {product_subject}, {campaign_name or "n/a"}.

CREATIVE BRIEF FROM THE USER
{brief_block}

{angle}

RULES
Create a clean commercial advertising visual.
Do not add random text, letters, logos, watermarks, mirrored writing, reversed characters, Arabic or English typography, headlines, captions, or unreadable lettering.
Do not paint words onto the image unless the creative brief explicitly asks for specific on-image text.
Focus on product placement, scene, composition, lighting, colors, style, background, and mood.
Do not invent prices, discounts, promo codes, URLs, or statistics.
""".strip()

    def _reference_image_for_attempt(self, campaign_content):
        # Product photos are not attached on the first attempt.
        # Tests may override this to verify the 3030 text-only retry.
        return None

    def _build_safe_retry_prompt(self, creative_brief):
        creative_brief = creative_brief or {}

        def line(label, value):
            value = self._clean(value)
            if not value:
                return ""
            return f"{label}: {value}\n"

        brief_block = "".join(
            [
                line("Focus", creative_brief.get("focus", "")),
                line("Style", creative_brief.get("style", "")),
                line("Colors", creative_brief.get("colors", "")),
                line("Background", creative_brief.get("background", "")),
                line("Composition", creative_brief.get("composition", "")),
                line("Mood", creative_brief.get("mood", "")),
                line(
                    "Additional visual instructions",
                    creative_brief.get("additional", ""),
                ),
            ]
        ).strip() or "Use a clean commercial product scene."

        return f"""
Create a clean commercial product advertising photograph.
No people unless explicitly required by the user.
No text, letters, logos, trademarks, labels, watermarks or typography.
Do not reproduce visible text from any reference.
Focus only on product form, scene, lighting, colors and composition.

VISUAL BRIEF
{brief_block}
""".strip()

    def generate_for_content(
        self,
        campaign_content,
        creative_brief=None,
        variation_index=1,
    ):
        creative_brief = creative_brief or {}
        fields = self._extract_fields(campaign_content.content_text)
        campaign_content._poster_variation = variation_index
        primary_prompt = self._build_primary_prompt(
            campaign_content,
            creative_brief,
            fields,
            variation_index=variation_index,
        )
        reference_image = self._reference_image_for_attempt(
            campaign_content
        )
        used_reference_image = bool(reference_image)
        logger.info(
            "Poster first attempt content_id=%s variation=%s "
            "used_reference_image=%s",
            getattr(campaign_content, "id", None),
            variation_index,
            used_reference_image,
        )
        logger.info(
            "Poster image prompt for content_id=%s variation=%s:\n%s",
            getattr(campaign_content, "id", None),
            variation_index,
            primary_prompt,
        )

        try:
            image_bytes = self._generate_image(
                primary_prompt,
                reference_image=reference_image,
            )
        except Exception as exc:
            cloudflare_exc = (
                exc.fallback_error
                if isinstance(exc, PosterProviderFallbackError)
                else exc
            )
            error_code = self._cloudflare_error_code(cloudflare_exc)
            logger.info(
                "Cloudflare image error content_id=%s code=%s http=%s",
                getattr(campaign_content, "id", None),
                error_code,
                self._cloudflare_http_status(cloudflare_exc),
            )
            if not self._is_cloudflare_flagged_error(cloudflare_exc):
                if isinstance(exc, PosterProviderFallbackError):
                    raise RuntimeError(str(exc)) from exc
                raise RuntimeError(
                    f"Cloudflare image generation failed: {exc}"
                ) from exc

            retry_prompt = self._build_safe_retry_prompt(creative_brief)
            logger.info(
                "Cloudflare moderation retry triggered content_id=%s "
                "previous_used_reference_image=%s",
                getattr(campaign_content, "id", None),
                used_reference_image,
            )
            logger.info(
                "Poster sanitized retry prompt for content_id=%s:\n%s",
                getattr(campaign_content, "id", None),
                retry_prompt,
            )
            try:
                image_bytes = self._generate_cloudflare_image(
                    retry_prompt,
                    reference_image=None,
                )
            except Exception as retry_exc:
                logger.info(
                    "Cloudflare moderation retry failed content_id=%s "
                    "code=%s http=%s",
                    getattr(campaign_content, "id", None),
                    self._cloudflare_error_code(retry_exc),
                    self._cloudflare_http_status(retry_exc),
                )
                raise PosterModerationRejected(
                    POSTER_MODERATION_USER_MESSAGE
                ) from retry_exc

        if not self._valid_image_bytes(image_bytes):
            raise RuntimeError(
                "Image generation returned an invalid image. "
                "No fallback poster was used."
            )

        filename = (
            f"campaign_{campaign_content.campaign.id}_"
            f"content_{campaign_content.id}_v{variation_index}.png"
        )
        campaign_content.poster.save(
            filename,
            ContentFile(image_bytes),
            save=True,
        )
        return campaign_content.poster

    @staticmethod
    def _valid_image_bytes(image_bytes):
        if not image_bytes:
            return False
        try:
            image = Image.open(BytesIO(image_bytes))
            image.verify()
            return True
        except Exception:
            return False
