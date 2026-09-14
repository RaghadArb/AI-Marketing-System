import os
import threading

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


_chart_lock = threading.Lock()


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

        with _chart_lock:
            figure = plt.figure(figsize=(8, 5))

            try:
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

                figure.savefig(
                    path,
                    bbox_inches="tight"
                )

            finally:
                plt.close(figure)
                plt.close("all")

        return path

    def create_ctr_chart(
        self,
        dataframe
    ):

        path = os.path.join(
            self.output_path,
            "ctr_performance.png"
        )

        with _chart_lock:
            figure = plt.figure(figsize=(8, 5))

            try:
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

                figure.savefig(
                    path,
                    bbox_inches="tight"
                )

            finally:
                plt.close(figure)
                plt.close("all")

        return path
