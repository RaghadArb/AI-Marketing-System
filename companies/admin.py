from django.contrib import admin
from .models import Company


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):

    list_display = (
        'company_name',
        'industry',
        'created_at'
    )

    search_fields = (
        'company_name',
        'industry'
    )

    list_filter = (
        'industry',
        'created_at'
    )

    ordering = (
        '-created_at',
    )