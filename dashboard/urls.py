from django.urls import path

from .views import (
    dashboard_home,

    companies_dashboard,
    company_create,
    company_edit,
    company_delete,

    campaigns_dashboard,
    campaign_analytics_dashboard,
    analytics_chart,

    ai_content_dashboard,
    products_dashboard,
    product_create,
    product_edit,
    product_delete,
    campaign_create,
    campaign_edit,
    campaign_delete,
    customer_support_dashboard,
    reports_dashboard,
    knowledge_base_dashboard,
    knowledge_document_create,
    knowledge_document_edit,
    knowledge_document_delete,
)


urlpatterns = [

    # Dashboard
    path(
        "",
        dashboard_home,
        name="dashboard_home"
    ),


    # ======================================================
    # COMPANIES
    # ======================================================

    path(
        "companies/",
        companies_dashboard,
        name="companies_dashboard"
    ),

    path(
        "companies/add/",
        company_create,
        name="company_create"
    ),

    path(
        "companies/<int:company_id>/edit/",
        company_edit,
        name="company_edit"
    ),

    path(
        "companies/<int:company_id>/delete/",
        company_delete,
        name="company_delete"
    ),


    # ======================================================
    # CAMPAIGNS
    # ======================================================

    path(
        "campaigns/",
        campaigns_dashboard,
        name="campaigns_dashboard"
    ),

    path(
        "campaign/<int:campaign_id>/analytics/",
        campaign_analytics_dashboard,
        name="campaign_analytics_dashboard"
    ),
    path(
    "campaigns/add/",
    campaign_create,
    name="campaign_create"
    ),

    path(
        "campaigns/<int:campaign_id>/edit/",
        campaign_edit,
        name="campaign_edit"
    ),

    path(
        "campaigns/<int:campaign_id>/delete/",
        campaign_delete,
        name="campaign_delete"
    ),

# ======================================================
# PRODUCTS
# ======================================================

    path(
        "products/",
        products_dashboard,
        name="products_dashboard"
    ),

    path(
        "products/add/",
        product_create,
        name="product_create"
    ),

    path(
        "products/<int:product_id>/edit/",
        product_edit,
        name="product_edit"
    ),

    path(
        "products/<int:product_id>/delete/",
        product_delete,
        name="product_delete"
    ),
    # ======================================================
    # ANALYTICS CHARTS
    # ======================================================

    path(
        "analytics/chart/<str:filename>/",
        analytics_chart,
        name="analytics_chart"
    ),


    # ======================================================
    # AI CONTENT
    # ======================================================

    path(
        "ai-content/",
        ai_content_dashboard,
        name="ai_content_dashboard"
    ),
    
    # ======================================================
    # CUSTOMER SUPPORT 
    # ======================================================
    path(
    "customer-support/",
    customer_support_dashboard,
    name="customer_support_dashboard"
    ),
    
    
    # ======================================================
    # REPORT GENERATION
    # ======================================================
    path(
    "reports/",
    reports_dashboard,
    name="reports_dashboard"
    ),
    
    # ======================================================
    # KNOWLEDGE BASE
    # ======================================================
    path(
    "knowledge-base/",
    knowledge_base_dashboard,
    name="knowledge_base_dashboard"
    ),

    path(
        "knowledge-base/add/",
        knowledge_document_create,
        name="knowledge_document_create"
    ),

    path(
        "knowledge-base/<int:document_id>/edit/",
        knowledge_document_edit,
        name="knowledge_document_edit"
    ),

    path(
        "knowledge-base/<int:document_id>/delete/",
        knowledge_document_delete,
        name="knowledge_document_delete"
    ),
]