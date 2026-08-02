import pandas as pd

from .metrics import (
    calculate_ctr,
    calculate_engagement_rate,
    calculate_total_engagement
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
                    "views": performance.views,
                    "clicks": performance.clicks,
                    "likes": performance.likes,
                    "shares": performance.shares,
                    "comments": performance.comments,
                    "date": performance.recorded_at,
                }
            )


        # Convert to dataFrame

        df = pd.DataFrame(data)


        if df.empty:
            return {
                "summary": {},
                "dataframe": df
            }
            
        df["date"] = df["date"].astype(str)

        # Metrics

        df["ctr"] = df.apply(
            lambda row: calculate_ctr(
                row["views"],
                row["clicks"]
            ),
            axis=1
        )


        df["engagement_rate"] = df.apply(
            lambda row: calculate_engagement_rate(
                row["views"],
                row["likes"],
                row["comments"],
                row["shares"]
            ),
            axis=1
        )


        df["total_engagement"] = df.apply(
            lambda row: calculate_total_engagement(
                row["likes"],
                row["comments"],
                row["shares"]
            ),
            axis=1
        )


        # Summary

        result = {

            "total_views": int(
                df["views"].sum()
            ),

            "total_clicks": int(
                df["clicks"].sum()
            ),

            "average_ctr": float(
                round(df["ctr"].mean(),
                2
                )
            ),

            "average_engagement_rate": float(
                round(df["engagement_rate"].mean(),
                2
                )
            ),

            "total_engagement": int(
                df["total_engagement"].sum()
            ),

            "best_platform": (
                df.groupby("platform")["total_engagement"]
                .sum()
                .idxmax()
            ),

        }


        return {
        "summary": result,
        "dataframe": df
        }