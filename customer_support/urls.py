from django.urls import path
from .views import send_support_message


urlpatterns = [

    path(
        "message/",
        send_support_message,
        name="send_support_message"
    ),

]