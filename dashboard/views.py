import os
import re

from django.conf import settings
from django.shortcuts import (
    render,
    get_object_or_404,
    redirect,
)
from django.http import FileResponse, Http404
from django.contrib import messages

from campaign.models import Campaign, CampaignContent
from companies.models import Company
from companies.forms import CompanyForm
from campaign.forms import CampaignForm

from ai_services.analytics.service import AnalyticsService
from ai_services.services.content_generator import ContentGenerator
from ai_services.services.instagram_publisher import (
    InstagramConfigError,
    InstagramPublishError,
    InstagramPublisher,
)
from ai_services.services.poster_generator import PosterGenerator

from .decorators import marketing_specialist_required

from products.models import Product
from products.forms import ProductForm

from customer_support.models import SupportConversation

from knowledge.models import KnowledgeDocument
from knowledge.forms import KnowledgeDocumentForm

# ==========================================================
# DASHBOARD HOME
# ==========================================================

@marketing_specialist_required
def dashboard_home(request):

    owned_campaigns = Campaign.objects.filter(
        company__owner=request.user
    ).select_related(
        "company",
        "product"
    )

    companies_count = Company.objects.filter(
        owner=request.user
    ).count()

    products_count = Product.objects.filter(
        company__owner=request.user
    ).count()

    campaigns_count = owned_campaigns.count()

    ai_contents_count = CampaignContent.objects.filter(
        campaign__company__owner=request.user,
        ai_generated=True
    ).count()

    recent_campaigns = owned_campaigns.order_by(
        "-created_at"
    )[:5]

    return render(
        request,
        "dashboard/home.html",
        {
            "companies_count": companies_count,
            "products_count": products_count,
            "campaigns_count": campaigns_count,
            "ai_contents_count": ai_contents_count,
            "recent_campaigns": recent_campaigns,
        }
    )


# ==========================================================
# COMPANY MANAGEMENT
# ==========================================================

@marketing_specialist_required
def companies_dashboard(request):

    companies = Company.objects.filter(
        owner=request.user
    ).order_by("-created_at")

    return render(
        request,
        "dashboard/companies.html",
        {
            "companies": companies,
        }
    )


@marketing_specialist_required
def company_create(request):

    if request.method == "POST":

        form = CompanyForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            company = form.save(
                commit=False
            )

            company.owner = request.user

            company.save()

            messages.success(
                request,
                "Company added successfully."
            )

            return redirect(
                "companies_dashboard"
            )

    else:

        form = CompanyForm()

    return render(
        request,
        "dashboard/company_form.html",
        {
            "form": form,
            "page_title": "Add Company",
            "button_text": "Add Company",
        }
    )


@marketing_specialist_required
def company_edit(
    request,
    company_id
):

    company = get_object_or_404(
        Company,
        id=company_id,
        owner=request.user
    )

    if request.method == "POST":

        form = CompanyForm(
            request.POST,
            request.FILES,
            instance=company
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Company updated successfully."
            )

            return redirect(
                "companies_dashboard"
            )

    else:

        form = CompanyForm(
            instance=company
        )

    return render(
        request,
        "dashboard/company_form.html",
        {
            "form": form,
            "company": company,
            "page_title": "Edit Company",
            "button_text": "Save Changes",
        }
    )


@marketing_specialist_required
def company_delete(
    request,
    company_id
):

    company = get_object_or_404(
        Company,
        id=company_id,
        owner=request.user
    )

    if request.method == "POST":

        company_name = (
            company.company_name
        )

        company.delete()

        messages.success(
            request,
            f"{company_name} deleted successfully."
        )

    return redirect(
        "companies_dashboard"
    )

# ==========================================================
# PRODUCT MANAGEMENT
# ==========================================================

@marketing_specialist_required
def products_dashboard(request):

    products = Product.objects.filter(
        company__owner=request.user
    ).select_related(
        "company"
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "dashboard/products.html",
        {
            "products": products,
        }
    )


@marketing_specialist_required
def product_create(request):

    if request.method == "POST":

        form = ProductForm(
            request.POST,
            request.FILES,
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Product added successfully."
            )

            return redirect(
                "products_dashboard"
            )

    else:

        form = ProductForm(
            user=request.user
        )

    return render(
        request,
        "dashboard/product_form.html",
        {
            "form": form,
            "page_title": "Add Product",
            "button_text": "Add Product",
        }
    )


@marketing_specialist_required
def product_edit(
    request,
    product_id
):

    product = get_object_or_404(
        Product,
        id=product_id,
        company__owner=request.user
    )

    if request.method == "POST":

        form = ProductForm(
            request.POST,
            request.FILES,
            instance=product,
            user=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Product updated successfully."
            )

            return redirect(
                "products_dashboard"
            )

    else:

        form = ProductForm(
            instance=product,
            user=request.user
        )

    return render(
        request,
        "dashboard/product_form.html",
        {
            "form": form,
            "product": product,
            "page_title": "Edit Product",
            "button_text": "Save Changes",
        }
    )


@marketing_specialist_required
def product_delete(
    request,
    product_id
):

    product = get_object_or_404(
        Product,
        id=product_id,
        company__owner=request.user
    )

    if request.method == "POST":

        product_name = (
            product.product_name
        )

        product.delete()

        messages.success(
            request,
            f"{product_name} deleted successfully."
        )

    return redirect(
        "products_dashboard"
    )
    
# ==========================================================
# CAMPAIGN MANAGEMENT
# ==========================================================

@marketing_specialist_required
def campaigns_dashboard(request):

    campaigns = Campaign.objects.filter(
        company__owner=request.user
    ).select_related(
        "company",
        "product"
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "dashboard/campaigns.html",
        {
            "campaigns": campaigns
        }
    )


@marketing_specialist_required
def campaign_create(request):

    if request.method == "POST":

        form = CampaignForm(
            request.POST,
            user=request.user
        )

        if form.is_valid():

            campaign = form.save(
                commit=False
            )

            # Security check:
            # ensure company belongs to logged-in user
            if campaign.company.owner != request.user:

                messages.error(
                    request,
                    "You cannot create a campaign for this company."
                )

            else:

                # If a product is selected,
                # it must belong to the selected company
                if (
                    campaign.product
                    and campaign.product.company != campaign.company
                ):

                    form.add_error(
                        "product",
                        "The selected product does not belong to the selected company."
                    )

                else:

                    campaign.save()

                    messages.success(
                        request,
                        "Campaign created successfully."
                    )

                    return redirect(
                        "campaigns_dashboard"
                    )

    else:

        form = CampaignForm(
            user=request.user
        )

    return render(
        request,
        "dashboard/campaign_form.html",
        {
            "form": form,
            "page_title": "Add Campaign",
            "button_text": "Add Campaign",
        }
    )


@marketing_specialist_required
def campaign_edit(
    request,
    campaign_id
):

    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        company__owner=request.user
    )

    if request.method == "POST":

        form = CampaignForm(
            request.POST,
            instance=campaign,
            user=request.user
        )

        if form.is_valid():

            updated_campaign = form.save(
                commit=False
            )

            if (
                updated_campaign.product
                and
                updated_campaign.product.company
                != updated_campaign.company
            ):

                form.add_error(
                    "product",
                    "The selected product does not belong to the selected company."
                )

            else:

                updated_campaign.save()

                messages.success(
                    request,
                    "Campaign updated successfully."
                )

                return redirect(
                    "campaigns_dashboard"
                )

    else:

        form = CampaignForm(
            instance=campaign,
            user=request.user
        )

    return render(
        request,
        "dashboard/campaign_form.html",
        {
            "form": form,
            "campaign": campaign,
            "page_title": "Edit Campaign",
            "button_text": "Save Changes",
        }
    )


@marketing_specialist_required
def campaign_delete(
    request,
    campaign_id
):

    campaign = get_object_or_404(
        Campaign,
        id=campaign_id,
        company__owner=request.user
    )

    if request.method == "POST":

        campaign_name = (
            campaign.campaign_name
        )

        campaign.delete()

        messages.success(
            request,
            f"{campaign_name} deleted successfully."
        )

    return redirect(
        "campaigns_dashboard"
    )


# ==========================================================
# CAMPAIGN ANALYTICS
# ==========================================================

@marketing_specialist_required
def campaign_analytics_dashboard(
    request,
    campaign_id
):

    campaign = get_object_or_404(
    Campaign,
    id=campaign_id,
    company__owner=request.user
    )

    analytics_service = (
        AnalyticsService()
    )

    result = (
        analytics_service
        .get_campaign_analytics(
            campaign
        )
    )

    chart_files = []

    for chart in result["charts"]:

        chart_files.append(
            os.path.basename(chart)
        )

    result["charts"] = (
        chart_files
    )

    return render(
        request,
        "dashboard/campaign_analytics.html",
        {
            "campaign": campaign,
            "analytics": result,
        }
    )


# ==========================================================
# ANALYTICS CHART FILES
# ==========================================================

@marketing_specialist_required
def analytics_chart(
    request,
    filename
):

    allowed_files = [
        "platform_engagement.png",
        "ctr_performance.png",
    ]

    if filename not in allowed_files:

        raise Http404()

    path = os.path.join(
        settings.BASE_DIR,
        "ai_data",
        "charts",
        filename
    )

    if not os.path.exists(path):

        raise Http404()

    return FileResponse(
        open(path, "rb"),
        content_type="image/png"
    )


# ==========================================================
# AI CONTENT GENERATION
# ==========================================================

@marketing_specialist_required
def ai_content_dashboard(request):

    campaigns = (
        Campaign.objects
        .filter(company__owner=request.user)
        .select_related("company", "product")
        .order_by("-created_at")
    )

    generated_suggestions = []
    selected_campaign = None
    error = None

    creative_brief = {
        "focus": "",
        "style": "Premium Product Ad",
        "colors": "",
        "background": "",
        "composition": "Product Centered",
        "mood": "",
        "additional": "",
    }

    if request.method == "POST":

        action = request.POST.get("action", "generate")

        if action == "generate":

            campaign_id = request.POST.get("campaign_id")

            creative_brief = {
                "focus": request.POST.get(
                    "creative_focus",
                    ""
                ).strip(),
                "style": request.POST.get(
                    "creative_style",
                    "Premium Product Ad"
                ).strip(),
                "colors": request.POST.get(
                    "creative_colors",
                    ""
                ).strip(),
                "background": request.POST.get(
                    "creative_background",
                    ""
                ).strip(),
                "composition": request.POST.get(
                    "creative_composition",
                    "Product Centered"
                ).strip(),
                "mood": request.POST.get(
                    "creative_mood",
                    ""
                ).strip(),
                "additional": request.POST.get(
                    "creative_additional",
                    ""
                ).strip(),
            }

            if not campaign_id:
                error = "Please select a campaign."

            elif not creative_brief["focus"]:
                error = (
                    "Please describe what the poster should focus on."
                )

            else:
                selected_campaign = get_object_or_404(
                    Campaign,
                    id=campaign_id,
                    company__owner=request.user
                )

                try:
                    generator = ContentGenerator()

                    result = generator.generate_campaign_content(
                        campaign=selected_campaign,
                        language="Arabic",
                        creative_brief=creative_brief,
                    )

                    content_text = result.get(
                        "content",
                        ""
                    ).strip()

                    validation = result.get(
                        "validation",
                        {}
                    )

                    is_valid = validation.get(
                        "is_valid",
                        False
                    )

                    validation_errors = validation.get(
                        "errors",
                        []
                    )

                    if not is_valid:

                        if validation_errors:
                            error = (
                                "AI content was rejected: "
                                + "; ".join(validation_errors)
                            )
                        else:
                            error = (
                                "AI content did not pass validation."
                            )

                    elif not content_text:
                        error = "The AI returned empty content."

                    else:
                        suggestion_sections = re.split(
                            r"(?=Suggestion\s+\d+\s*)",
                            content_text,
                            flags=re.IGNORECASE
                        )

                        suggestion_sections = [
                            section.strip()
                            for section in suggestion_sections
                            if section.strip()
                            and re.match(
                                r"Suggestion\s+\d+",
                                section.strip(),
                                flags=re.IGNORECASE
                            )
                        ]

                        if len(suggestion_sections) != 3:
                            error = (
                                "The AI response passed validation but could not "
                                "be separated into exactly 3 suggestions."
                            )

                        else:
                            poster_generator = PosterGenerator()
                            created_contents = []
                            poster_failures = []

                            for index, section in enumerate(
                                suggestion_sections,
                                start=1
                            ):
                                title_match = re.search(
                                    r"Title\s*:\s*(.+)",
                                    section,
                                    flags=re.IGNORECASE
                                )

                                suggestion_title = (
                                    title_match.group(1).strip()
                                    if title_match
                                    else f"Suggestion {index}"
                                )

                                saved_content = (
                                    CampaignContent.objects.create(
                                        campaign=selected_campaign,
                                        title=suggestion_title,
                                        content_text=section,
                                        content_type="Post",
                                        platform=selected_campaign.platform,
                                        language="Arabic",
                                        ai_generated=True,
                                        is_selected=False,
                                        is_published=False
                                    )
                                )

                                try:
                                    poster_generator.generate_for_content(
                                        saved_content,
                                        creative_brief=creative_brief,
                                    )

                                except Exception as poster_error:
                                    poster_failures.append(
                                        f"Suggestion {index}: "
                                        f"{poster_error}"
                                    )

                                created_contents.append(
                                    saved_content
                                )

                            generated_suggestions = [
                                {
                                    "id": item.id,
                                    "title": item.title,
                                    "content": item.content_text,
                                    "poster_url": (
                                        item.poster.url
                                        if item.poster
                                        else None
                                    ),
                                    "is_selected": item.is_selected,
                                    "is_published": item.is_published,
                                    "instagram_permalink": (
                                        item.instagram_permalink
                                    ),
                                    "publish_error": item.publish_error,
                                }
                                for item in created_contents
                            ]

                            if poster_failures:
                                messages.warning(
                                    request,
                                    "The text suggestions were saved, "
                                    "but one or more posters could not "
                                    "be generated. "
                                    + " | ".join(poster_failures)
                                )

                            else:
                                messages.success(
                                    request,
                                    "3 AI suggestions and matching "
                                    "creative-brief posters were generated, "
                                    "validated and saved successfully."
                                )

                except Exception as e:
                    error = str(e)

        elif action == "edit":

            content_id = request.POST.get("content_id")
            new_title = request.POST.get(
                "title",
                ""
            ).strip()
            new_content = request.POST.get(
                "content_text",
                ""
            ).strip()

            campaign_content = get_object_or_404(
                CampaignContent,
                id=content_id,
                campaign__company__owner=request.user
            )

            selected_campaign = campaign_content.campaign

            if not new_content:
                error = "Content cannot be empty."

            else:
                if new_title:
                    campaign_content.title = new_title

                campaign_content.content_text = new_content

                campaign_content.save(
                    update_fields=[
                        "title",
                        "content_text"
                    ]
                )

                messages.success(
                    request,
                    "Suggestion updated successfully."
                )

        elif action == "select":

            content_id = request.POST.get(
                "content_id"
            )

            campaign_content = get_object_or_404(
                CampaignContent,
                id=content_id,
                campaign__company__owner=request.user
            )

            selected_campaign = campaign_content.campaign

            CampaignContent.objects.filter(
                campaign=selected_campaign,
                is_selected=True
            ).update(
                is_selected=False
            )

            campaign_content.is_selected = True

            campaign_content.save(
                update_fields=[
                    "is_selected"
                ]
            )

            messages.success(
                request,
                "Suggestion selected successfully."
            )

        elif action == "publish_instagram":

            content_id = request.POST.get(
                "content_id"
            )

            campaign_content = get_object_or_404(
                CampaignContent,
                id=content_id,
                campaign__company__owner=request.user
            )

            selected_campaign = campaign_content.campaign

            if not campaign_content.is_selected:
                messages.error(
                    request,
                    "Select this suggestion before publishing "
                    "to Instagram."
                )

            elif campaign_content.is_published:
                messages.error(
                    request,
                    "This suggestion has already been published "
                    "to Instagram."
                )

            else:
                try:
                    InstagramPublisher().publish(
                        campaign_content
                    )
                    campaign_content.refresh_from_db()
                    messages.success(
                        request,
                        "The selected content was published "
                        "to Instagram."
                    )

                except (
                    InstagramConfigError,
                    InstagramPublishError
                ) as publish_error:
                    messages.error(
                        request,
                        str(publish_error)
                    )

                except Exception:
                    messages.error(
                        request,
                        "Instagram publishing failed. "
                        "The suggestion was not marked as published."
                    )

        if (
            selected_campaign
            and action in [
                "edit",
                "select",
                "publish_instagram",
            ]
        ):
            latest_contents = list(
                CampaignContent.objects.filter(
                    campaign=selected_campaign,
                    ai_generated=True,
                    language="Arabic"
                ).order_by(
                    "-created_at"
                )[:3]
            )

            latest_contents.reverse()

            generated_suggestions = [
                {
                    "id": item.id,
                    "title": item.title,
                    "content": item.content_text,
                    "poster_url": (
                        item.poster.url
                        if item.poster
                        else None
                    ),
                    "is_selected": item.is_selected,
                    "is_published": item.is_published,
                    "instagram_permalink": (
                        item.instagram_permalink
                    ),
                    "publish_error": item.publish_error,
                }
                for item in latest_contents
            ]

    return render(
        request,
        "dashboard/ai_content.html",
        {
            "campaigns": campaigns,
            "generated_suggestions": generated_suggestions,
            "selected_campaign": selected_campaign,
            "creative_brief": creative_brief,
            "error": error,
        }
    )
    

# ==========================================================
# CUSTOMER SUPPORT
# ==========================================================
    
@marketing_specialist_required
def customer_support_dashboard(request):

    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")

    selected_company = None
    conversations = []
    support_analytics = None
    error = None

    company_id = request.GET.get("company")

    if company_id:

        selected_company = get_object_or_404(
            Company,
            id=company_id,
            owner=request.user
        )

        conversations = (
            SupportConversation.objects
            .filter(company=selected_company)
            .prefetch_related("messages")
            .order_by("-started_at")
        )

        try:

            analytics_service = AnalyticsService()

            support_analytics = (
                analytics_service.get_support_analytics(
                    selected_company
                )
            )

        except Exception as e:

            error = str(e)

    return render(
        request,
        "dashboard/customer_support.html",
        {
            "companies": companies,
            "selected_company": selected_company,
            "conversations": conversations,
            "support_analytics": support_analytics,
            "error": error,
        }
    )
    
    
# ==========================================================
# REPORT GENERATION
# ==========================================================
    
@marketing_specialist_required
def reports_dashboard(request):

    campaigns = Campaign.objects.filter(
        company__owner=request.user
    ).select_related(
        "company",
        "product"
    ).order_by(
        "-created_at"
    )

    selected_campaign = None
    report_data = None
    error = None

    campaign_id = request.GET.get("campaign")

    if campaign_id:

        selected_campaign = get_object_or_404(
            Campaign,
            id=campaign_id,
            company__owner=request.user
        )

        try:

            analytics_service = AnalyticsService()

            analytics = analytics_service.get_campaign_analytics(
                selected_campaign
            )

            report_data = {
                "summary": analytics["summary"],
                "report": analytics["report"],
            }

        except Exception as e:

            error = str(e)

    return render(
        request,
        "dashboard/reports.html",
        {
            "campaigns": campaigns,
            "selected_campaign": selected_campaign,
            "report_data": report_data,
            "error": error,
        }
    )
    # ==========================================================
# KNOWLEDGE BASE
# ==========================================================

@marketing_specialist_required
def knowledge_base_dashboard(request):

    documents = KnowledgeDocument.objects.filter(
        company__owner=request.user
    ).select_related(
        "company"
    ).order_by(
        "-uploaded_at"
    )

    return render(
        request,
        "dashboard/knowledge_base.html",
        {
            "documents": documents
        }
    )


@marketing_specialist_required
def knowledge_document_create(request):

    if request.method == "POST":

        form = KnowledgeDocumentForm(
            request.POST,
            request.FILES,
            user=request.user
        )

        if form.is_valid():

            document = form.save(
                commit=False
            )

            if document.company.owner != request.user:

                messages.error(
                    request,
                    "You cannot add documents for this company."
                )

            else:

                document.save()

                messages.success(
                    request,
                    "Knowledge document uploaded successfully."
                )

                return redirect(
                    "knowledge_base_dashboard"
                )

    else:

        form = KnowledgeDocumentForm(
            user=request.user
        )

    return render(
        request,
        "dashboard/knowledge_form.html",
        {
            "form": form,
            "page_title": "Add Knowledge Document",
            "button_text": "Upload Document",
        }
    )


@marketing_specialist_required
def knowledge_document_edit(
    request,
    document_id
):

    document = get_object_or_404(
        KnowledgeDocument,
        id=document_id,
        company__owner=request.user
    )

    if request.method == "POST":

        form = KnowledgeDocumentForm(
            request.POST,
            request.FILES,
            instance=document,
            user=request.user
        )

        if form.is_valid():

            updated_document = form.save(
                commit=False
            )

            if updated_document.company.owner != request.user:

                messages.error(
                    request,
                    "You cannot assign this document to that company."
                )

            else:

                updated_document.save()

                messages.success(
                    request,
                    "Knowledge document updated successfully."
                )

                return redirect(
                    "knowledge_base_dashboard"
                )

    else:

        form = KnowledgeDocumentForm(
            instance=document,
            user=request.user
        )

    return render(
        request,
        "dashboard/knowledge_form.html",
        {
            "form": form,
            "document": document,
            "page_title": "Edit Knowledge Document",
            "button_text": "Save Changes",
        }
    )


@marketing_specialist_required
def knowledge_document_delete(
    request,
    document_id
):

    document = get_object_or_404(
        KnowledgeDocument,
        id=document_id,
        company__owner=request.user
    )

    if request.method == "POST":

        title = document.title

        document.delete()

        messages.success(
            request,
            f"{title} deleted successfully."
        )

    return redirect(
        "knowledge_base_dashboard"
    )