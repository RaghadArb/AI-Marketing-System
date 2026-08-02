from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .models import SupportConversation
from .services import CustomerSupportService



@csrf_exempt
def send_support_message(request):

    if request.method == "POST":

        data = json.loads(
            request.body
        )

        conversation_id = data.get(
            "conversation_id"
        )

        message_text = data.get(
            "message"
        )


        conversation = SupportConversation.objects.get(
            id=conversation_id
        )


        service = CustomerSupportService()


        ai_message = service.process_message(
            conversation=conversation,
            message_text=message_text
        )


        return JsonResponse(
            {
                "response": ai_message.message_text
            }
        )


    return JsonResponse(
        {
            "error": "POST request required"
        },
        status=400
    )