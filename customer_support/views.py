import json

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from companies.models import Company

from .models import SupportConversation
from .services import CustomerSupportService


MAX_CUSTOMER_MESSAGE_LENGTH = 2000


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

        if not request.user.is_authenticated:
            raise Http404()

        conversation = get_object_or_404(
            SupportConversation,
            id=conversation_id,
            company__owner=request.user
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


@ensure_csrf_cookie
def customer_support_chat(request, company_id):

    company = get_object_or_404(
        Company,
        id=company_id
    )

    return render(
        request,
        "customer_support/chat.html",
        {
            "company": company,
        }
    )


def _read_customer_payload(request):

    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or b"{}")
        except ValueError:
            return {}

    return {
        "conversation_id": request.POST.get("conversation_id"),
        "message": request.POST.get("message"),
    }


@require_POST
def customer_send_message(request, company_id):

    company = get_object_or_404(
        Company,
        id=company_id
    )

    data = _read_customer_payload(request)
    message_text = str(data.get("message") or "").strip()

    if not message_text:
        return JsonResponse(
            {"error": "Message cannot be empty."},
            status=400
        )

    if len(message_text) > MAX_CUSTOMER_MESSAGE_LENGTH:
        return JsonResponse(
            {"error": "Message is too long."},
            status=400
        )

    conversation_id = data.get("conversation_id") or None

    if conversation_id:
        conversation = get_object_or_404(
            SupportConversation,
            id=conversation_id,
            company=company
        )
    else:
        conversation = SupportConversation.objects.create(
            company=company
        )

    try:
        ai_message = CustomerSupportService().process_message(
            conversation=conversation,
            message_text=message_text
        )
    except Exception:
        return JsonResponse(
            {
                "error": (
                    "The support assistant is unavailable right now. "
                    "Please try again later."
                ),
                "conversation_id": conversation.id,
            },
            status=502
        )

    return JsonResponse(
        {
            "conversation_id": conversation.id,
            "response": ai_message.message_text,
        }
    )
