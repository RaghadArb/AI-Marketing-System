from django.contrib import admin
from .models import SupportConversation, SupportMessage

admin.site.register(SupportConversation)
admin.site.register(SupportMessage)