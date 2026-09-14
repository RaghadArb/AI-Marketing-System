import pandas as pd

from .metrics import (
    calculate_aggregate_ctr,
    calculate_ctr,
    calculate_engagement_rate,
    calculate_total_engagement,
)


class PerformanceAnalyzer:

    def analyze_campaign(self, campaign):

        performances = campaign.performance.all()

        data = []

        for performance in performances:

            data.append(
                {
                    "platform": performance.platform,
                    "language": performance.language,
                    "views": performance.views or 0,
                    "clicks": performance.clicks or 0,
                    "likes": performance.likes or 0,
                    "shares": performance.shares or 0,
                    "comments": performance.comments or 0,
                    "impressions": performance.impressions,
                    "reach": performance.reach,
                    "saves": performance.saves,
                    "date": performance.recorded_at,
                }
            )

        df = pd.DataFrame(data)

        if df.empty:
            return {
                "summary": {},
                "dataframe": df,
            }

        df["date"] = df["date"].astype(str)

        def row_ctr(row):
            if pd.notna(row.get("impressions")) and row["impressions"]:
                return calculate_ctr(row["impressions"], row["clicks"])
            return calculate_ctr(row["views"], row["clicks"])

        df["ctr"] = df.apply(row_ctr, axis=1)

        df["engagement_rate"] = df.apply(
            lambda row: calculate_engagement_rate(
                row["views"],
                row["likes"],
                row["comments"],
                row["shares"],
            ),
            axis=1,
        )

        df["total_engagement"] = df.apply(
            lambda row: calculate_total_engagement(
                row["likes"],
                row["comments"],
                row["shares"],
            ),
            axis=1,
        )

        total_views = int(df["views"].sum())
        total_clicks = int(df["clicks"].sum())
        impressions_series = df["impressions"].dropna()
        total_impressions = (
            int(impressions_series.sum())
            if not impressions_series.empty
            else None
        )

        if total_impressions:
            average_ctr = calculate_aggregate_ctr(
                total_clicks,
                total_impressions,
            )
            ctr_basis = "impressions"
        else:
            average_ctr = calculate_aggregate_ctr(
                total_clicks,
                total_views,
            )
            ctr_basis = "views" if total_views else None

        result = {
            "total_views": total_views,
            "total_clicks": total_clicks,
            "total_impressions": total_impressions,
            "total_reach": (
                int(df["reach"].dropna().sum())
                if not df["reach"].dropna().empty
                else None
            ),
            "average_ctr": average_ctr,
            "ctr_basis": ctr_basis,
            "average_engagement_rate": (
                float(
                    round(
                        (int(df["total_engagement"].sum()) / total_views) * 100,
                        2,
                    )
                )
                if total_views
                else None
            ),
            "total_engagement": int(df["total_engagement"].sum()),
            "best_platform": (
                df.groupby("platform")["total_engagement"]
                .sum()
                .idxmax()
            ),
        }

        return {
            "summary": result,
            "dataframe": df,
        }
