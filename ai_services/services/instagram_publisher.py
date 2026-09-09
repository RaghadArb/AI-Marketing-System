import os
import re
from io import BytesIO
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone
from PIL import Image

from ai_services.clients.instagram_client import (
    InstagramAPIError,
    InstagramClient,
)


INSTAGRAM_CAPTION_LIMIT = 2200


class InstagramConfigError(RuntimeError):
    """Missing or invalid Instagram publishing configuration."""


class InstagramPublishError(RuntimeError):
    """Publishing was refused or the Graph API call failed."""


class InstagramPublisher:

    def __init__(self, client=None):
        self.client = client or InstagramClient()

    @staticmethod
    def _clean(value):
        if value is None:
            return ""

        return " ".join(
            str(value).replace("\x00", " ").split()
        ).strip()

    def _extract_fields(self, content_text):
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
                flags=re.IGNORECASE | re.DOTALL,
            )

            if match:
                fields[key] = self._clean(match.group(1))

        return fields

    def build_caption(self, campaign_content):
        fields = self._extract_fields(
            campaign_content.content_text
        )
        parts = [
            fields["caption"] or self._clean(campaign_content.title),
            fields["cta"],
            fields["hashtags"],
        ]
        caption = "\n\n".join(
            part for part in parts if part
        ).strip()

        if len(caption) > INSTAGRAM_CAPTION_LIMIT:
            caption = caption[:INSTAGRAM_CAPTION_LIMIT].rstrip()

        return caption

    @staticmethod
    def validate_public_base_url(base_url):
        base = (base_url or "").strip()

        if not base:
            raise InstagramConfigError(
                "Instagram publishing is not configured. "
                "Set INSTAGRAM_PUBLIC_MEDIA_BASE_URL."
            )

        lowered = base.lower()

        if not lowered.startswith("https://"):
            raise InstagramConfigError(
                "INSTAGRAM_PUBLIC_MEDIA_BASE_URL must start with https://."
            )

        if "localhost" in lowered or "127.0.0.1" in lowered:
            raise InstagramConfigError(
                "INSTAGRAM_PUBLIC_MEDIA_BASE_URL cannot use localhost."
            )

        return base.rstrip("/")

    def _public_jpeg_url(self, relative_path):
        base = self.validate_public_base_url(
            getattr(
                settings,
                "INSTAGRAM_PUBLIC_MEDIA_BASE_URL",
                "",
            )
        )
        media_url = str(
            getattr(settings, "MEDIA_URL", "/media/")
        )

        if not media_url.endswith("/"):
            media_url += "/"

        return urljoin(
            base + "/",
            media_url.lstrip("/") + relative_path.lstrip("/"),
        )

    def prepare_jpeg(self, campaign_content):
        poster = campaign_content.poster

        if not poster:
            raise InstagramPublishError(
                "This suggestion has no poster image to publish."
            )

        try:
            poster.open("rb")
            image_bytes = poster.read()
        finally:
            try:
                poster.close()
            except Exception:
                pass

        image = Image.open(BytesIO(image_bytes))
        image = image.convert("RGB")
        image.thumbnail((1080, 1080))

        relative_name = (
            f"instagram_publish/content_{campaign_content.id}.jpg"
        )
        output_path = os.path.join(
            str(settings.MEDIA_ROOT),
            relative_name.replace("/", os.sep),
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(
            output_path,
            format="JPEG",
            quality=85,
            optimize=True,
        )

        return relative_name

    def _save_error(self, campaign_content, message):
        campaign_content.is_published = False
        campaign_content.publish_error = message
        campaign_content.save(
            update_fields=["is_published", "publish_error"]
        )

    def publish(self, campaign_content):
        if not campaign_content.is_selected:
            message = (
                "Select this suggestion before publishing to Instagram."
            )
            self._save_error(campaign_content, message)
            raise InstagramPublishError(message)

        if campaign_content.is_published:
            raise InstagramPublishError(
                "This suggestion has already been published to Instagram."
            )

        if not campaign_content.poster:
            message = (
                "This suggestion has no poster image to publish."
            )
            self._save_error(campaign_content, message)
            raise InstagramPublishError(message)

        if not self.client.is_configured():
            message = (
                "Instagram publishing is not configured. "
                "Set META_ACCESS_TOKEN and "
                "INSTAGRAM_BUSINESS_ACCOUNT_ID."
            )
            self._save_error(campaign_content, message)
            raise InstagramConfigError(message)

        try:
            self.validate_public_base_url(
                getattr(
                    settings,
                    "INSTAGRAM_PUBLIC_MEDIA_BASE_URL",
                    "",
                )
            )
            jpeg_relative = self.prepare_jpeg(campaign_content)
            image_url = self._public_jpeg_url(jpeg_relative)

            if "localhost" in image_url.lower() or "127.0.0.1" in image_url:
                raise InstagramConfigError(
                    "The generated Instagram image URL cannot use localhost."
                )

            caption = self.build_caption(campaign_content)
            container_id = self.client.create_image_container(
                image_url=image_url,
                caption=caption,
            )

            try:
                status = self.client.get_container_status(
                    container_id
                )
            except InstagramAPIError:
                status = ""

            if str(status).upper() == "ERROR":
                raise InstagramAPIError(
                    "Instagram rejected the media container."
                )

            media_id = self.client.publish_container(
                container_id
            )

            permalink = ""

            try:
                permalink = self.client.get_permalink(media_id)
            except InstagramAPIError:
                permalink = ""

        except (InstagramConfigError, InstagramPublishError) as exc:
            self._save_error(campaign_content, str(exc))
            raise
        except InstagramAPIError as exc:
            message = str(exc)
            self._save_error(campaign_content, message)
            raise InstagramPublishError(message) from None
        except Exception:
            message = (
                "Instagram publishing failed due to an unexpected error."
            )
            self._save_error(campaign_content, message)
            raise InstagramPublishError(message) from None

        campaign_content.is_published = True
        campaign_content.instagram_media_id = media_id
        campaign_content.instagram_permalink = permalink
        campaign_content.published_at = timezone.now()
        campaign_content.publish_error = ""
        campaign_content.save(
            update_fields=[
                "is_published",
                "instagram_media_id",
                "instagram_permalink",
                "published_at",
                "publish_error",
            ]
        )

        return campaign_content
