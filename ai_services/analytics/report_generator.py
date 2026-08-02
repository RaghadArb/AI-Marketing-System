class ReportGenerator:

# generates both campaign reports and customer support reports


    def generate_campaign_report(
        self,
        summary
    ):

        insights = []
        recommendations = []


        best_platform = summary.get(
            "best_platform"
        )


        if best_platform:

            insights.append(
                f"Best performing platform is {best_platform}."
            )

            recommendations.append(
                f"Consider focusing more budget on {best_platform}."
            )



        ctr = summary.get(
            "average_ctr",
            0
        )


        if ctr < 2:

            insights.append(
                "CTR is low."
            )

            recommendations.append(
                "Improve call-to-action and campaign message."
            )


        elif ctr < 5:

            insights.append(
                "CTR is acceptable but can be improved."
            )


        else:

            insights.append(
                "CTR performance is strong."
            )



        engagement = summary.get(
            "average_engagement_rate",
            0
        )


        if engagement < 3:

            recommendations.append(
                "Improve content quality to increase engagement."
            )


        elif engagement >= 10:

            insights.append(
                "Audience engagement is high."
            )


        return {

            "insights": insights,

            "recommendations": recommendations

        }





    def generate_support_report(
        self,
        summary
    ):

        insights = []
        recommendations = []



        total_messages = summary.get(
            "total_messages",
            0
        )


        customer_messages = summary.get(
            "customer_messages",
            0
        )


        ai_messages = summary.get(
            "ai_messages",
            0
        )



        if total_messages:

            customer_ratio = round(
                (customer_messages / total_messages) * 100,
                2
            )


            insights.append(
                f"Customers generated {customer_ratio}% of messages."
            )



        if ai_messages >= customer_messages:

            insights.append(
                "AI responses are handling the majority of conversation messages."
            )



        average_messages = summary.get(
            "average_messages_per_conversation",
            0
        )


        if average_messages > 10:

            recommendations.append(
                "Long conversations detected. Improve the knowledge base and FAQs."
            )


        elif average_messages <= 3:

            insights.append(
                "Support conversations are generally short."
            )



        common_words = summary.get(
            "most_common_words",
            []
        )


        if common_words:

            topics = [
                word[0]
                for word in common_words[:5]
            ]


            insights.append(
                f"Common customer topics: {', '.join(topics)}."
            )



        return {

            "insights": insights,

            "recommendations": recommendations

        }