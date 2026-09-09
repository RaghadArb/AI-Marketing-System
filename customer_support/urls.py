from django.urls import path

from .views import (
    customer_send_message,
    customer_support_chat,
    send_support_message,
)


urlpatterns = [

    path(
        "message/",
        send_support_message,
        name="send_support_message"
    ),

    path(
        "company/<int:company_id>/",
        customer_support_chat,
        name="customer_support_chat"
    ),

    path(
        "company/<int:company_id>/message/",
        customer_send_message,
        name="customer_send_message"
    ),

]
