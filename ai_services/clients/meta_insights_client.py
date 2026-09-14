from ai_services.clients.instagram_client import (
    InstagramAPIError,
    InstagramClient,
)


class MetaInsightsError(InstagramAPIError):
    """Raised when a Meta insights/read request fails."""


class MetaInsightsClient:
    """Read-only Graph API helper for Instagram media and Facebook posts."""

    def __init__(self, client=None):
        self.client = client or InstagramClient()

    def instagram_ready(self):
        return self.client.is_configured()

    def facebook_ready(self):
        return bool(self.client.access_token and self.client.page_id)

    def _get(self, path, params=None):
        query = dict(params or {})
        query.setdefault("access_token", self.client.access_token)
        try:
            return self.client._request("GET", path, params=query)
        except InstagramAPIError as exc:
            raise MetaInsightsError(str(exc)) from None

    def list_instagram_media(self, limit=12):
        if not self.instagram_ready():
            raise MetaInsightsError(
                "Instagram account credentials are not configured."
            )
        result = self._get(
            f"{self.client.ig_user_id}/media",
            params={
                "fields": (
                    "id,caption,media_type,timestamp,permalink,"
                    "thumbnail_url,media_url,like_count,comments_count"
                ),
                "limit": int(limit),
            },
        )
        data = result.get("data") if isinstance(result, dict) else None
        return data if isinstance(data, list) else []

    def instagram_insights(self, media_id, metrics):
        if not media_id or not metrics:
            return {}
        try:
            result = self._get(
                f"{media_id}/insights",
                params={"metric": ",".join(metrics)},
            )
        except MetaInsightsError:
            return {}
        rows = result.get("data") if isinstance(result, dict) else None
        values = {}
        if not isinstance(rows, list):
            return values
        for row in rows:
            name = str(row.get("name") or "").strip()
            series = row.get("values") or []
            if not name or not series:
                continue
            raw = series[-1].get("value") if isinstance(series[-1], dict) else None
            if isinstance(raw, (int, float)):
                values[name] = int(raw)
        return values

    def list_facebook_posts(self, limit=12):
        if not self.facebook_ready():
            raise MetaInsightsError(
                "Facebook Page credentials are not configured."
            )
        result = self._get(
            f"{self.client.page_id}/posts",
            params={
                "fields": (
                    "id,message,created_time,permalink_url,full_picture,"
                    "shares,likes.summary(true),comments.summary(true)"
                ),
                "limit": int(limit),
            },
        )
        data = result.get("data") if isinstance(result, dict) else None
        return data if isinstance(data, list) else []

    def facebook_insights(self, post_id, metrics):
        if not post_id or not metrics:
            return {}
        try:
            result = self._get(
                f"{post_id}/insights",
                params={"metric": ",".join(metrics)},
            )
        except MetaInsightsError:
            return {}
        rows = result.get("data") if isinstance(result, dict) else None
        values = {}
        if not isinstance(rows, list):
            return values
        for row in rows:
            name = str(row.get("name") or "").strip()
            series = row.get("values") or []
            if not name or not series:
                continue
            raw = series[-1].get("value") if isinstance(series[-1], dict) else None
            if isinstance(raw, (int, float)):
                values[name] = int(raw)
        return values
