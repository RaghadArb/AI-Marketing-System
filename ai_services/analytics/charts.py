import matplotlib.pyplot as plt
import os


class AnalyticsCharts:

    def __init__(self):

        self.output_path = "ai_data/charts"

        os.makedirs(
            self.output_path,
            exist_ok=True
        )


    def create_platform_performance_chart(
        self,
        dataframe
    ):

        path = os.path.join(
            self.output_path,
            "platform_engagement.png"
        )

        plt.figure(figsize=(8, 5))

        # No performance data yet
        if (
            dataframe.empty
            or "platform" not in dataframe.columns
            or "total_engagement" not in dataframe.columns
        ):

            plt.text(
                0.5,
                0.5,
                "No campaign performance data available yet.",
                horizontalalignment="center",
                verticalalignment="center",
                fontsize=14
            )

            plt.axis("off")

        else:

            platform_data = (
                dataframe
                .groupby("platform")["total_engagement"]
                .sum()
            )

            platform_data.plot(
                kind="bar"
            )

            plt.title(
                "Engagement by Platform"
            )

            plt.xlabel(
                "Platform"
            )

            plt.ylabel(
                "Engagement"
            )

        plt.savefig(
            path,
            bbox_inches="tight"
        )

        plt.close()

        return path


    def create_ctr_chart(
        self,
        dataframe
    ):

        path = os.path.join(
            self.output_path,
            "ctr_performance.png"
        )

        plt.figure(figsize=(8, 5))

        # No performance data yet
        if (
            dataframe.empty
            or "ctr" not in dataframe.columns
        ):

            plt.text(
                0.5,
                0.5,
                "No CTR performance data available yet.",
                horizontalalignment="center",
                verticalalignment="center",
                fontsize=14
            )

            plt.axis("off")

        else:

            dataframe["ctr"].plot(
                kind="line",
                marker="o"
            )

            plt.title(
                "CTR Performance"
            )

            plt.xlabel(
                "Performance Record"
            )

            plt.ylabel(
                "CTR %"
            )

        plt.savefig(
            path,
            bbox_inches="tight"
        )

        plt.close()

        return path