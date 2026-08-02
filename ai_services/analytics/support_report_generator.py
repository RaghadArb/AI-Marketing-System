class SupportReportGenerator:


    def generate_report(
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


        # Message distribution

        if total_messages > 0:

            customer_ratio = round(
                (customer_messages / total_messages) * 100,
                2
            )

            insights.append(
                f"Customers generated {customer_ratio}% of total messages."
            )


        # AI response ratio

        if ai_messages > customer_messages:

            insights.append(
                "AI handled more responses than customer messages."
            )


        # Conversation length

        avg_messages = summary.get(
            "average_messages_per_conversation",
            0
        )


        if avg_messages > 10:

            recommendations.append(
                "Long conversations detected. Improve FAQ and knowledge base coverage."
            )

        elif avg_messages <= 3:

            insights.append(
                "Conversations are generally short."
            )


        # Common topics

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
                f"Most common customer terms: {', '.join(topics)}."
            )


        return {

            "insights": insights,

            "recommendations": recommendations

        }