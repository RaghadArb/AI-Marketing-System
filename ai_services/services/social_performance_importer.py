from datetime import datetime, timedelta, timezone

from django.conf import settings

from campaign.models import CampaignPerformance
from ai_services.clients.meta_insights_client import (
    MetaInsightsClient,
    MetaInsightsError,
)


METRIC_KEYS = (
    "impressions",
    "reach",
    "likes",
    "comments",
    "shares",
    "saved",
    "video_views",
    "clicks",
)

# CampaignPerformance fields that exist today.
STORED_METRIC_MAP = {
    "likes": "likes",
    "comments": "comments",
    "shares": "shares",
    "video_views": "views",
    "clicks": "clicks",
    "impressions": "impressions",
    "reach": "reach",
    "saved": "saves",
}


class SocialPerformanceImporter:
    """Fetch, normalize, and import selected social posts into CampaignPerformance."""

    def __init__(self, insights_client=None):
        self.insights_client = insights_client

    @staticmethod
    def mode():
        value = str(
            getattr(settings, "SOCIAL_PERFORMANCE_MODE", "demo") or "demo"
        ).strip().lower()
        return value if value in ("demo", "live") else "demo"

    def connection_status(self, live_verified=False):
        mode = self.mode()
        if mode == "demo":
            return {
                "state": "demo",
                "label": "Demo mode",
                "detail": (
                    "Simulated social-media performance for demonstration."
                ),
            }
        client = self._client()
        if not (client.instagram_ready() or client.facebook_ready()):
            return {
                "state": "not_configured",
                "label": "Meta credentials not configured",
                "detail": (
                    "Live Instagram/Facebook read access is not configured."
                ),
            }
        if live_verified:
            return {
                "state": "live",
                "label": "Live Meta connection available",
                "detail": "A Meta Graph API read request succeeded.",
            }
        return {
            "state": "credentials_present",
            "label": "Meta credentials present",
            "detail": (
                "Credentials are configured. Connection is confirmed only "
                "after Fetch Social Posts succeeds."
            ),
        }

    def _client(self):
        if self.insights_client is None:
            self.insights_client = MetaInsightsClient()
        return self.insights_client

    @staticmethod
    def _metric(value):
        if value in (None, ""):
            return None
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        if number < 0:
            return None
        return number

    def _empty_metrics(self):
        return {key: None for key in METRIC_KEYS}

    def normalize_instagram(self, payload, insights=None, source="live"):
        payload = payload or {}
        insights = insights or {}
        metrics = self._empty_metrics()
        metrics["likes"] = self._metric(
            insights.get("likes")
            or payload.get("like_count")
        )
        metrics["comments"] = self._metric(
            insights.get("comments")
            or payload.get("comments_count")
        )
        metrics["impressions"] = self._metric(insights.get("impressions"))
        metrics["reach"] = self._metric(insights.get("reach"))
        metrics["saved"] = self._metric(insights.get("saved"))
        metrics["video_views"] = self._metric(
            insights.get("video_views")
            or insights.get("plays")
        )
        media_type = str(payload.get("media_type") or "IMAGE").upper()
        if media_type in ("VIDEO", "REELS") and metrics["video_views"] is None:
            metrics["video_views"] = self._metric(insights.get("views"))
        permalink = str(payload.get("permalink") or "").strip()
        return {
            "platform": "instagram",
            "external_post_id": str(payload.get("id") or "").strip(),
            "caption": str(payload.get("caption") or "").strip(),
            "media_type": media_type,
            "published_at": str(payload.get("timestamp") or "").strip(),
            "permalink": permalink,
            "thumbnail_url": str(
                payload.get("thumbnail_url")
                or payload.get("media_url")
                or ""
            ).strip(),
            "metrics": metrics,
            "source": source,
        }

    def normalize_facebook(self, payload, insights=None, source="live"):
        payload = payload or {}
        insights = insights or {}
        likes_summary = payload.get("likes") or {}
        comments_summary = payload.get("comments") or {}
        shares = payload.get("shares") or {}
        if isinstance(likes_summary, dict):
            likes_summary = (likes_summary.get("summary") or {}).get(
                "total_count"
            )
        if isinstance(comments_summary, dict):
            comments_summary = (comments_summary.get("summary") or {}).get(
                "total_count"
            )
        if isinstance(shares, dict):
            shares = shares.get("count")

        metrics = self._empty_metrics()
        metrics["impressions"] = self._metric(
            insights.get("post_impressions")
            or insights.get("post_impressions_organic")
        )
        metrics["reach"] = self._metric(
            insights.get("post_impressions_unique")
        )
        metrics["clicks"] = self._metric(
            insights.get("post_clicks")
            or insights.get("post_engaged_users")
        )
        metrics["likes"] = self._metric(likes_summary)
        metrics["comments"] = self._metric(comments_summary)
        metrics["shares"] = self._metric(shares)
        return {
            "platform": "facebook",
            "external_post_id": str(payload.get("id") or "").strip(),
            "caption": str(payload.get("message") or "").strip(),
            "media_type": "POST",
            "published_at": str(payload.get("created_time") or "").strip(),
            "permalink": str(payload.get("permalink_url") or "").strip(),
            "thumbnail_url": str(payload.get("full_picture") or "").strip(),
            "metrics": metrics,
            "source": source,
        }

    def demo_posts(self, campaign=None):
        product_name = ""
        campaign_name = ""
        if campaign is not None:
            campaign_name = campaign.campaign_name
            if campaign.product_id:
                product_name = campaign.product.product_name
        now = datetime.now(timezone.utc)
        product_label = product_name or campaign_name or "the product"
        posts = [
            self.normalize_instagram(
                {
                    "id": "demo-ig-launch",
                    "caption": (
                        f"Product launch: {product_label}. "
                        "New campaign drop this week."
                    ),
                    "media_type": "IMAGE",
                    "timestamp": (now - timedelta(days=4)).isoformat(),
                    "permalink": "https://www.instagram.com/p/demo-launch/",
                    "thumbnail_url": "",
                    "like_count": 522,
                    "comments_count": 41,
                },
                insights={
                    "impressions": 8120,
                    "reach": 5410,
                    "saved": 96,
                },
                source="demo",
            ),
            self.normalize_instagram(
                {
                    "id": "demo-ig-reel",
                    "caption": (
                        f"Promotional reel for {product_label}. "
                        "See how the offer works."
                    ),
                    "media_type": "REELS",
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                    "permalink": "https://www.instagram.com/reel/demo-reel/",
                    "thumbnail_url": "",
                    "like_count": 310,
                    "comments_count": 22,
                },
                insights={
                    "impressions": 9400,
                    "reach": 6200,
                    "plays": 6203,
                    "saved": 54,
                },
                source="demo",
            ),
            self.normalize_instagram(
                {
                    "id": "demo-ig-offer",
                    "caption": (
                        f"Limited offer on {product_label}. "
                        "Tap to learn more."
                    ),
                    "media_type": "IMAGE",
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "permalink": "https://www.instagram.com/p/demo-offer/",
                    "thumbnail_url": "",
                    "like_count": 188,
                    "comments_count": 14,
                },
                insights={
                    "impressions": 4100,
                    "reach": 2880,
                    "saved": 27,
                },
                source="demo",
            ),
            self.normalize_facebook(
                {
                    "id": "demo-fb-announce",
                    "message": (
                        f"Campaign announcement: {campaign_name or product_label} "
                        "is live. Join the conversation."
                    ),
                    "created_time": (now - timedelta(days=3)).isoformat(),
                    "permalink_url": "https://www.facebook.com/demo/announce",
                    "full_picture": "",
                    "likes": {"summary": {"total_count": 196}},
                    "comments": {"summary": {"total_count": 18}},
                    "shares": {"count": 12},
                },
                insights={
                    "post_impressions": 5200,
                    "post_impressions_unique": 2880,
                    "post_clicks": 74,
                },
                source="demo",
            ),
            self.normalize_facebook(
                {
                    "id": "demo-fb-promo",
                    "message": (
                        f"Weekend promotion for {product_label}. "
                        "Share with a friend."
                    ),
                    "created_time": (now - timedelta(hours=18)).isoformat(),
                    "permalink_url": "https://www.facebook.com/demo/promo",
                    "full_picture": "",
                    "likes": {"summary": {"total_count": 142}},
                    "comments": {"summary": {"total_count": 9}},
                    "shares": {"count": 7},
                },
                insights={
                    "post_impressions": 3600,
                    "post_impressions_unique": 2104,
                    "post_clicks": 41,
                },
                source="demo",
            ),
        ]
        for post in posts:
            post["match"] = self.suggest_match(campaign, post)
        return posts

    def fetch_posts(self, platforms, campaign=None):
        wanted = self._normalize_platforms(platforms)
        mode = self.mode()
        if mode == "demo":
            posts = [
                post for post in self.demo_posts(campaign)
                if post["platform"] in wanted
            ]
            return {
                "source": "demo",
                "posts": posts,
                "error": None,
            }

        client = self._client()
        posts = []
        errors = []
        if "instagram" in wanted:
            if not client.instagram_ready():
                errors.append(
                    "Instagram credentials are not configured for live fetch."
                )
            else:
                try:
                    media = client.list_instagram_media()
                    insight_names = [
                        "impressions",
                        "reach",
                        "likes",
                        "comments",
                        "saved",
                        "plays",
                        "views",
                        "video_views",
                    ]
                    for item in media:
                        media_id = str(item.get("id") or "")
                        insights = client.instagram_insights(
                            media_id,
                            insight_names,
                        )
                        posts.append(
                            self.normalize_instagram(
                                item,
                                insights=insights,
                                source="live",
                            )
                        )
                except MetaInsightsError as exc:
                    errors.append(str(exc))
        if "facebook" in wanted:
            if not client.facebook_ready():
                errors.append(
                    "Facebook Page credentials are not configured "
                    "for live fetch."
                )
            else:
                try:
                    page_posts = client.list_facebook_posts()
                    insight_names = [
                        "post_impressions",
                        "post_impressions_unique",
                        "post_clicks",
                    ]
                    for item in page_posts:
                        post_id = str(item.get("id") or "")
                        insights = client.facebook_insights(
                            post_id,
                            insight_names,
                        )
                        posts.append(
                            self.normalize_facebook(
                                item,
                                insights=insights,
                                source="live",
                            )
                        )
                except MetaInsightsError as exc:
                    errors.append(str(exc))

        for post in posts:
            post["match"] = self.suggest_match(campaign, post)

        error = None
        if errors and not posts:
            error = " ".join(errors)
        elif errors:
            error = " ".join(errors)
        elif not posts:
            error = "No social posts were returned for the selected platforms."

        return {
            "source": "live",
            "posts": posts,
            "error": error,
        }

    @staticmethod
    def _normalize_platforms(platforms):
        if platforms in (None, "", "both"):
            return {"instagram", "facebook"}
        if isinstance(platforms, (list, tuple, set)):
            values = {str(item).strip().lower() for item in platforms}
        else:
            values = {str(platforms).strip().lower()}
        allowed = {"instagram", "facebook"}
        selected = values & allowed
        return selected or allowed

    def suggest_match(self, campaign, post):
        if campaign is None:
            return {"level": "Low", "reason": "No campaign context."}
        score = 0
        reasons = []
        caption = str(post.get("caption") or "").lower()
        platform = str(post.get("platform") or "").lower()
        campaign_platform = str(campaign.platform or "").lower()
        if platform and platform in campaign_platform:
            score += 2
            reasons.append("platform")
        tokens = []
        for raw in (
            campaign.campaign_name,
            campaign.objective,
            getattr(campaign.product, "product_name", "") if campaign.product_id else "",
        ):
            tokens.extend(
                part.lower()
                for part in str(raw or "").replace(",", " ").split()
                if len(part) > 3
            )
        hits = [token for token in set(tokens) if token in caption]
        if hits:
            score += min(3, len(hits))
            reasons.append("caption")
        published = self._parse_date(post.get("published_at"))
        if published and campaign.start_date and campaign.end_date:
            if campaign.start_date <= published <= campaign.end_date:
                score += 2
                reasons.append("dates")
        elif published and campaign.start_date and published >= campaign.start_date:
            score += 1
            reasons.append("dates")
        if score >= 4:
            level = "High"
        elif score >= 2:
            level = "Medium"
        else:
            level = "Low"
        return {
            "level": level,
            "reason": ", ".join(reasons) or "No strong overlap.",
        }

    @staticmethod
    def _parse_date(value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    @staticmethod
    def display_platform(platform):
        value = str(platform or "").strip().lower()
        if value == "instagram":
            return "Instagram"
        if value == "facebook":
            return "Facebook"
        return str(platform or "").strip()

    def already_imported_keys(self, campaign):
        rows = CampaignPerformance.objects.filter(
            campaign=campaign,
        ).exclude(external_post_id="")
        return {
            (row.platform, row.external_post_id)
            for row in rows
        }

    def is_imported(self, campaign, post):
        post_id = str(post.get("external_post_id") or "").strip()
        if not post_id:
            return False
        platform = self.display_platform(post.get("platform"))
        return CampaignPerformance.objects.filter(
            campaign=campaign,
            platform=platform,
            external_post_id=post_id,
        ).exists()

    def stored_fields_from_post(self, post):
        metrics = post.get("metrics") or {}
        payload = {
            "platform": self.display_platform(post.get("platform")),
            "language": "Arabic",
            "views": 0,
            "clicks": 0,
            "likes": 0,
            "shares": 0,
            "comments": 0,
            "source": str(post.get("source") or "").strip(),
            "external_post_id": str(post.get("external_post_id") or "").strip(),
            "impressions": None,
            "reach": None,
            "saves": None,
            "social_permalink": str(post.get("permalink") or "").strip(),
            "social_media_type": str(post.get("media_type") or "").strip(),
        }
        stored_any = bool(payload["external_post_id"])
        for source, field in STORED_METRIC_MAP.items():
            value = self._metric(metrics.get(source))
            if value is None:
                continue
            payload[field] = value
            stored_any = True
        return payload, stored_any

    def import_selected(self, campaign, posts, selected_ids, already_imported=None):
        selected = [str(item) for item in selected_ids if str(item).strip()]
        if not selected:
            return {
                "imported": 0,
                "skipped_duplicate": 0,
                "imported_ids": [],
                "error": "Select at least one post to import.",
            }

        by_key = {}
        for post in posts:
            post_id = str(post.get("external_post_id") or "").strip()
            if not post_id:
                continue
            platform = str(post.get("platform") or "").strip().lower()
            by_key[(platform, post_id)] = post
            by_key[post_id] = post

        imported_ids = []
        skipped = 0
        for raw_id in selected:
            platform = None
            post_id = raw_id
            if ":" in raw_id:
                platform, post_id = raw_id.split(":", 1)
                platform = platform.strip().lower()
                post_id = post_id.strip()
            post = None
            if platform:
                post = by_key.get((platform, post_id))
            if post is None:
                post = by_key.get(post_id)
            if post is None:
                continue
            payload, stored_any = self.stored_fields_from_post(post)
            if not stored_any:
                continue
            if self.is_imported(campaign, post):
                skipped += 1
                continue
            CampaignPerformance.objects.create(
                campaign=campaign,
                **payload,
            )
            imported_ids.append(payload["external_post_id"])

        if not imported_ids and skipped:
            error = "Selected posts were already imported for this campaign."
        elif not imported_ids:
            error = (
                "None of the selected posts could be imported. "
                "They may be missing or have no matching performance fields."
            )
        else:
            error = None

        return {
            "imported": len(imported_ids),
            "skipped_duplicate": skipped,
            "imported_ids": imported_ids,
            "error": error,
        }
