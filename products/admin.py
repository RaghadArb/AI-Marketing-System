from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):

    list_display = (
        'product_name',
        'company',
        'category',
        'price',
        'status',
        'created_at'
    )

    list_filter = (
        'category',
        'status',
        'created_at'
    )

    search_fields = (
        'product_name',
        'category',
        'company__company_name'
    )

    ordering = (
        '-created_at',
    )