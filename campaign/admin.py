from django.contrib import admin, messages
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.utils.html import format_html

from .models import Campaign, CampaignContent, CampaignPerformance


class CampaignContentInline(admin.TabularInline):

    model = CampaignContent

    extra = 0

    readonly_fields = (
        "title",
        "content_text",
        "language",
        "platform",
        "ai_generated",
        "created_at",
    )

    can_delete = False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):

    inlines = [
        CampaignContentInline,
    ]

    list_display = (
        "campaign_name",
        "company",
        "product",
        "platform",
        "status",
        "budget",
        "start_date",
        "end_date",
        "created_at",
        "generate_ai_button",
    )

    list_filter = (
        "platform",
        "status",
        "created_at",
    )

    search_fields = (
        "campaign_name",
        "company__company_name",
        "product__product_name",
    )

    ordering = (
        "-created_at",
    )


    def generate_ai_button(self, obj):

        return format_html(
            '<a class="button" href="{}">Generate AI Content</a>',
            f"{obj.id}/generate-ai/"
        )


    generate_ai_button.short_description = "AI Generation"


    def get_urls(self):

        urls = super().get_urls()

        custom_urls = [
            path(
                "<int:campaign_id>/generate-ai/",
                self.admin_site.admin_view(
                    self.generate_ai_content
                ),
                name="generate_ai_content",
            ),
        ]

        return custom_urls + urls


    def generate_ai_content(
        self,
        request,
        campaign_id
    ):
        get_object_or_404(
            Campaign,
            id=campaign_id
        )

        messages.info(
            request,
            "AI content is generated from the dashboard only: "
            "Creative Brief → 3 suggestions → validation → posters."
        )

        return redirect(
            request.META.get(
                "HTTP_REFERER",
                "../"
            )
        )


@admin.register(CampaignContent)
class CampaignContentAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "campaign",
        "content_type",
        "platform",
        "language",
        "ai_generated",
        "is_selected",
        "is_published",
        "created_at",
    )

    list_filter = (
        "content_type",
        "platform",
        "language",
        "ai_generated",
        "is_selected",
        "is_published",
    )

    search_fields = (
        "title",
        "content_text",
        "campaign__campaign_name",
    )

    ordering = (
        "-created_at",
    )


@admin.register(CampaignPerformance)
class CampaignPerformanceAdmin(admin.ModelAdmin):

    list_display = (
        "campaign",
        "platform",
        "views",
        "clicks",
        "likes",
        "shares",
        "comments",
        "recorded_at",
    )

    list_filter = (
        "platform",
        "recorded_at",
    )

    search_fields = (
        "campaign__campaign_name",
    )

    ordering = (
        "-recorded_at",
    )