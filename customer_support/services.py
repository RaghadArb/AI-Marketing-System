from ai_services.rag.support_agent import SupportAgent
from .models import SupportMessage


class CustomerSupportService:


    def __init__(self):

        self.agent = SupportAgent()



    def process_message(
        self,
        conversation,
        message_text
    ):


        # Save customer message

        customer_message = SupportMessage.objects.create(
            conversation=conversation,
            sender="Customer",
            message_text=message_text
        )


        # Get company from conversation

        company_id = conversation.company.id



        # Generate AI answer

        ai_response = self.agent.generate_answer(
            question=message_text,
            company_id=company_id
        )



        # Save AI message

        ai_message = SupportMessage.objects.create(
            conversation=conversation,
            sender="AI",
            message_text=ai_response
        )


        return ai_message