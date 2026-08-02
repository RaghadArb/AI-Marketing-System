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

        platform_data = (
            dataframe
            .groupby("platform")["total_engagement"]
            .sum()
        )


        plt.figure(
            figsize=(8,5)
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


        path = os.path.join(
            self.output_path,
            "platform_engagement.png"
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

        plt.figure(
            figsize=(8,5)
        )


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


        path = os.path.join(
            self.output_path,
            "ctr_performance.png"
        )


        plt.savefig(
            path,
            bbox_inches="tight"
        )


        plt.close()


        return path