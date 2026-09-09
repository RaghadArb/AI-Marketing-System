import requests
from django.conf import settings


class InstagramAPIError(RuntimeError):
    """Raised when the Meta Graph API request fails."""


def _redact_secrets(text, token=""):
    message = str(text or "")

    if token:
        message = message.replace(token, "[redacted]")

    return message


class InstagramClient:
    """
    Official Meta Graph API client for Instagram image publishing.
    """

    def __init__(self):
        self.access_token = getattr(
            settings,
            "META_ACCESS_TOKEN",
            "",
        ) or ""
        self.ig_user_id = getattr(
            settings,
            "INSTAGRAM_BUSINESS_ACCOUNT_ID",
            "",
        ) or ""
        self.graph_version = getattr(
            settings,
            "META_GRAPH_API_VERSION",
            "v21.0",
        ) or "v21.0"
        self.page_id = getattr(
            settings,
            "FACEBOOK_PAGE_ID",
            "",
        ) or ""

    def is_configured(self):
        return bool(
            self.access_token
            and self.ig_user_id
        )

    def _graph_url(self, path):
        version = str(self.graph_version).strip("/")
        path = str(path).lstrip("/")
        return (
            f"https://graph.facebook.com/{version}/{path}"
        )

    def _request(self, method, path, data=None, params=None):
        url = self._graph_url(path)
        payload = dict(data or {})
        query = dict(params or {})

        try:
            response = requests.request(
                method,
                url,
                data=payload or None,
                params=query or None,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise InstagramAPIError(
                "Instagram Graph API connection failed: "
                + _redact_secrets(exc, self.access_token)
            ) from None

        try:
            body = response.json()
        except ValueError:
            body = {"error": response.text}

        if not response.ok or (
            isinstance(body, dict)
            and body.get("error")
        ):
            error = body.get("error", body)

            if isinstance(error, dict):
                detail = (
                    error.get("message")
                    or error.get("error_user_msg")
                    or "Graph API request failed."
                )
            else:
                detail = str(error)

            raise InstagramAPIError(
                "Instagram Graph API failed: "
                + _redact_secrets(detail, self.access_token)
            )

        return body

    def create_image_container(self, image_url, caption=""):
        result = self._request(
            "POST",
            f"{self.ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self.access_token,
            },
        )
        container_id = result.get("id")

        if not container_id:
            raise InstagramAPIError(
                "Instagram Graph API did not return a media container ID."
            )

        return str(container_id)

    def get_container_status(self, container_id):
        result = self._request(
            "GET",
            str(container_id),
            params={
                "fields": "status_code",
                "access_token": self.access_token,
            },
        )
        return result.get("status_code") or ""

    def publish_container(self, container_id):
        result = self._request(
            "POST",
            f"{self.ig_user_id}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": self.access_token,
            },
        )
        media_id = result.get("id")

        if not media_id:
            raise InstagramAPIError(
                "Instagram Graph API did not return a published media ID."
            )

        return str(media_id)

    def get_permalink(self, media_id):
        result = self._request(
            "GET",
            str(media_id),
            params={
                "fields": "permalink",
                "access_token": self.access_token,
            },
        )
        permalink = result.get("permalink") or ""

        return str(permalink).strip()
