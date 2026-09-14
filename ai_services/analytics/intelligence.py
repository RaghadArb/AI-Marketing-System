from collections import defaultdict

from .metrics import calculate_aggregate_ctr


class CampaignIntelligence:
    """Deterministic campaign funnel, diagnosis, and comparisons. No LLM."""

    def build(self, campaign, summary, performances):
        summary = summary or {}
        rows = list(performances or [])
        funnel = self.build_funnel(summary)
        comparison = self.build_comparison(rows)
        diagnosis = self.build_diagnosis(summary, funnel, comparison, rows)
        return {
            "funnel": funnel,
            "diagnosis": diagnosis,
            "comparison": comparison,
            "metrics": self.visible_metrics(campaign, summary),
        }

    def visible_metrics(self, campaign, summary):
        summary = summary or {}
        metrics = [
            ("Impressions", summary.get("total_impressions")),
            ("Views", summary.get("total_views")),
            ("Clicks", summary.get("total_clicks")),
            ("CTR", self._pct(summary.get("average_ctr"))),
            ("Engagement", summary.get("total_engagement")),
            ("Engagement rate", self._pct(summary.get("average_engagement_rate"))),
            ("Reach", summary.get("total_reach")),
            ("Conversions", None),
            ("Conversion rate", None),
            ("Revenue", None),
            ("ROI", None),
            ("Cost per click", None),
            ("Cost per conversion", None),
        ]
        if campaign.budget is not None:
            metrics.append(("Campaign budget", str(campaign.budget)))
        return [
            {"label": label, "value": value, "available": value not in (None, "")}
            for label, value in metrics
        ]

    @staticmethod
    def _pct(value):
        if value in (None, ""):
            return None
        return f"{value}%"

    def build_funnel(self, summary):
        impressions = summary.get("total_impressions")
        clicks = summary.get("total_clicks")
        funnel_ctr = (
            calculate_aggregate_ctr(clicks, impressions)
            if impressions
            else None
        )
        stages = []
        if impressions is not None:
            stages.append(
                {
                    "name": "Impressions",
                    "value": impressions,
                    "available": True,
                }
            )
        if clicks is not None or impressions is not None:
            stages.append(
                {
                    "name": "Clicks",
                    "value": clicks if clicks is not None else 0,
                    "available": clicks is not None,
                    "rate_label": "CTR",
                    "rate": funnel_ctr,
                }
            )
        stages.append(
            {
                "name": "Conversions",
                "value": None,
                "available": False,
            }
        )
        stages.append(
            {
                "name": "Revenue",
                "value": None,
                "available": False,
            }
        )

        bottleneck = (
            "Conversion and revenue stages are not available "
            "in the current performance schema."
        )
        if impressions and clicks is not None:
            drop = 1 - (clicks / impressions) if impressions else 0
            if drop >= 0.9:
                bottleneck = (
                    "Visibility is recorded, but the largest drop occurs "
                    "between impressions and clicks."
                )
            else:
                bottleneck = (
                    "Click-through is present relative to impressions. "
                    "Conversion data is not recorded, so later funnel "
                    "drop-off cannot be measured."
                )
        elif impressions:
            bottleneck = (
                "Impressions are recorded, but clicks are missing or zero."
            )
        return {
            "stages": stages,
            "bottleneck": bottleneck,
            "ctr": funnel_ctr,
            "click_to_conversion": None,
        }

    def build_comparison(self, rows):
        platforms = defaultdict(lambda: {
            "clicks": 0,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "impressions": 0,
            "impression_rows": 0,
            "count": 0,
        })
        posts = []
        for row in rows:
            bucket = platforms[row.platform or "Other"]
            bucket["clicks"] += row.clicks or 0
            bucket["views"] += row.views or 0
            bucket["likes"] += row.likes or 0
            bucket["comments"] += row.comments or 0
            bucket["shares"] += row.shares or 0
            bucket["count"] += 1
            if row.impressions is not None:
                bucket["impressions"] += row.impressions
                bucket["impression_rows"] += 1
            if row.external_post_id:
                denom = row.impressions if row.impressions else row.views
                ctr = (
                    round((row.clicks / denom) * 100, 2)
                    if denom
                    else None
                )
                engagement = (
                    (row.likes or 0) + (row.comments or 0) + (row.shares or 0)
                )
                posts.append(
                    {
                        "label": row.external_post_id,
                        "platform": row.platform,
                        "clicks": row.clicks or 0,
                        "views": row.views or 0,
                        "impressions": row.impressions,
                        "ctr": ctr,
                        "engagement": engagement,
                    }
                )

        platform_rows = []
        for name, bucket in platforms.items():
            denom = (
                bucket["impressions"]
                if bucket["impression_rows"]
                else bucket["views"]
            )
            ctr = round((bucket["clicks"] / denom) * 100, 2) if denom else None
            engagement = bucket["likes"] + bucket["comments"] + bucket["shares"]
            platform_rows.append(
                {
                    "label": name,
                    "clicks": bucket["clicks"],
                    "views": bucket["views"],
                    "impressions": (
                        bucket["impressions"]
                        if bucket["impression_rows"]
                        else None
                    ),
                    "ctr": ctr,
                    "engagement": engagement,
                }
            )

        best_platform = None
        reason = None
        if len(platform_rows) >= 2:
            ranked = sorted(
                platform_rows,
                key=lambda item: (
                    item["ctr"] is not None,
                    item["ctr"] or 0,
                    item["engagement"],
                ),
                reverse=True,
            )
            best_platform = ranked[0]["label"]
            reason = (
                "Higher recorded CTR and/or engagement than the other "
                "platform(s) in this campaign."
            )
        best_post = None
        if len(posts) >= 2:
            ranked_posts = sorted(
                posts,
                key=lambda item: (
                    item["ctr"] is not None,
                    item["ctr"] or 0,
                    item["engagement"],
                    item["clicks"],
                ),
                reverse=True,
            )
            best_post = ranked_posts[0]
        return {
            "platforms": platform_rows,
            "posts": posts,
            "best_platform": best_platform,
            "best_post": best_post,
            "reason": reason,
            "can_compare_platforms": len(platform_rows) >= 2,
            "can_compare_posts": len(posts) >= 2,
        }

    def build_diagnosis(self, summary, funnel, comparison, rows):
        if not rows:
            return {
                "status": "Insufficient Data",
                "strengths": [],
                "weaknesses": [
                    "No campaign performance records are available."
                ],
                "funnel_bottleneck": funnel.get("bottleneck"),
                "metric_observations": [],
            }

        strengths = []
        weaknesses = []
        observations = []
        if comparison.get("can_compare_platforms") and comparison.get("best_platform"):
            strengths.append(
                f"{comparison['best_platform']} recorded a stronger relative result."
            )
            others = [
                item["label"]
                for item in comparison["platforms"]
                if item["label"] != comparison["best_platform"]
            ]
            if others:
                weaknesses.append(
                    "Relative underperformance on: " + ", ".join(others) + "."
                )
        if funnel.get("ctr") is not None:
            observations.append(f"Recorded CTR is {funnel['ctr']}%.")
        if summary.get("total_impressions") is not None:
            observations.append(
                f"Recorded impressions: {summary['total_impressions']}."
            )
        observations.append(
            "Conversions and revenue are not available in the current schema."
        )
        if impressions := summary.get("total_impressions"):
            clicks_value = summary.get("total_clicks") or 0
            if impressions and clicks_value == 0:
                status = "Needs Attention"
            elif comparison.get("can_compare_platforms"):
                status = "Strong" if strengths else "Moderate"
            else:
                status = "Moderate"
        elif comparison.get("can_compare_platforms"):
            status = "Strong" if strengths else "Moderate"
        elif summary.get("total_clicks") or summary.get("total_views"):
            status = "Moderate"
        else:
            status = "Needs Attention"
        if not strengths and not comparison.get("can_compare_platforms"):
            weaknesses.append(
                "Not enough platform or post variety for a relative comparison."
            )
        return {
            "status": status,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "funnel_bottleneck": funnel.get("bottleneck"),
            "metric_observations": observations,
        }

    def strategy_vs_outcome(self, strategy, summary, diagnosis):
        if not strategy:
            return {
                "available": False,
                "planned_objective": None,
                "actual_outcome": None,
                "assessment": (
                    "No saved strategy context is available for this campaign."
                ),
            }
        objective = (
            strategy.get("campaign_objective")
            or strategy.get("strategy_summary")
            or ""
        ).strip()
        parts = []
        if summary.get("total_impressions") is not None:
            parts.append(f"impressions {summary['total_impressions']}")
        if summary.get("total_clicks") is not None:
            parts.append(f"clicks {summary['total_clicks']}")
        if summary.get("average_ctr") is not None:
            parts.append(f"CTR {summary['average_ctr']}%")
        outcome = (
            "Recorded outcome: " + ", ".join(parts)
            if parts
            else "Recorded outcome metrics are limited."
        )
        assessment = (
            "No numeric KPI target was stored, so achievement cannot be claimed. "
        )
        if diagnosis.get("funnel_bottleneck"):
            assessment += diagnosis["funnel_bottleneck"]
        return {
            "available": True,
            "planned_objective": objective or "Not specified",
            "actual_outcome": outcome,
            "assessment": assessment,
        }

    def combined_context(self, campaign, voice):
        if not voice or voice.get("empty"):
            return None
        period = bool(campaign.start_date or campaign.end_date)
        return {
            "label": (
                "Customer Support Signals During Campaign Period"
                if period and voice.get("filtered_to_campaign_dates")
                else "Company Customer Voice Context"
            ),
            "caution": (
                "Support conversations are linked to the company, not to "
                "this campaign. They are context only and are not evidence "
                "that the campaign caused those questions."
            ),
            "topics": (voice.get("topics") or [])[:5],
            "concerns": (voice.get("concerns") or [])[:5],
            "questions": (voice.get("questions") or [])[:5],
            "insufficient_data": bool(voice.get("insufficient_data")),
        }
