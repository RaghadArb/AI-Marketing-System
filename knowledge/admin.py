from django.contrib import admin

from .models import KnowledgeDocument


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'company',
        'document_type',
        'uploaded_at'
    )

    list_filter = (
        'document_type',
        'uploaded_at'
    )

    search_fields = (
        'title',
        'description',
        'company__company_name'
    )

    ordering = (
        '-uploaded_at',
    )