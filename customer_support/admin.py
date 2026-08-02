from django.contrib import admin

from .models import (
    SupportConversation,
    SupportMessage
)


@admin.register(SupportConversation)
class SupportConversationAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'company',
        'started_at'
    )

    list_filter = (
        'company',
        'started_at'
    )

    search_fields = (
        'company__company_name',
    )

    ordering = (
        '-started_at',
    )


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):

    list_display = (
        'conversation',
        'sender',
        'message_text',
        'created_at'
    )

    list_filter = (
        'sender',
        'created_at'
    )

    search_fields = (
        'message_text',
    )

    ordering = (
        '-created_at',
    )