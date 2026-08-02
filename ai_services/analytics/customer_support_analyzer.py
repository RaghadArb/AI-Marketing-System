import pandas as pd
from collections import Counter
import re


class CustomerSupportAnalyzer:


    def analyze_company_support(
        self,
        company
    ):

        conversations = (
            company.support_conversations
            .prefetch_related("messages")
            .all()
        )


        data = []


        for conversation in conversations:

            for message in conversation.messages.all():

                data.append(
                    {
                        "conversation_id": conversation.id,
                        "sender": message.sender,
                        "message_text": message.message_text,
                        "created_at": str(message.created_at)
                    }
                )


        df = pd.DataFrame(data)


        if df.empty:

            return {
                "summary": {},
                "dataframe": df
            }



        # Number of conversations

        total_conversations = (
            df["conversation_id"]
            .nunique()
        )


        # Number of messages

        total_messages = len(df)


        # Average messages per conversation

        average_messages_per_conversation = round(
            total_messages / total_conversations,
            2
        )



        # Sender distribution

        customer_messages = (
            df[
                df["sender"] == "Customer"
            ]
            .shape[0]
        )


        ai_messages = (
            df[
                df["sender"] == "AI"
            ]
            .shape[0]
        )



        # Extract customer message topics

        customer_text = " ".join(
            df[
                df["sender"] == "Customer"
            ]["message_text"]
            .tolist()
        )


        words = re.findall(
            r"\b\w+\b",
            customer_text.lower()
        )


        most_common_words = Counter(
            words
        ).most_common(10)



        summary = {

            "total_conversations": int(
                total_conversations
            ),

            "total_messages": int(
                total_messages
            ),

            "average_messages_per_conversation": (
                average_messages_per_conversation
            ),

            "customer_messages": int(
                customer_messages
            ),

            "ai_messages": int(
                ai_messages
            ),

            "most_common_words": (
                most_common_words
            )

        }



        return {

            "summary": summary,

            "dataframe": df

        }