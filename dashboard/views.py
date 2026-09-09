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
from ai_services.rag.ingestion import DocumentIngestionService
from ai_services.rag.vector_store import VectorStore
from ai_services.services.campaign_advisor import CampaignAdvisor
from ai_services.services.content_generator import ContentGenerator
from ai_services.services.instagram_publisher import (
    InstagramConfigError,
    InstagramPublishError,
    InstagramPublisher,
)
from ai_services.services.poster_generator import PosterGenerator

from .decorators import marketing_specialist_required
from .presentation import parse_suggestion_display
from .workspace import (
    limit_campaign_form_to_company,
    limit_form_to_company,
    redirect_company_scope,
    workspace_context,
    workspace_id_from_request,
)

from products.models import Product
from products.forms import ProductForm

from customer_support.models import SupportConversation, SupportMessage

from knowledge.models import KnowledgeDocument
from knowledge.forms import KnowledgeDocumentForm


INSTAGRAM_LIVE_CONNECTION_MESSAGE = (
    "Instagram publishing is available but requires a connected "
    "Meta Developer account. Live account connection is not "
    "configured in this environment."
)


def _instagram_is_configured():
    return InstagramPublisher().client.is_configured()


def _safe_instagram_publish_error(message):
    text = str(message or "").strip()

    if not text:
        return ""

    lowered = text.lower()
    technical_markers = (
        "meta_access_token",
        "instagram_business_account_id",
        "instagram_public_media_base_url",
        "access_token",
        "graph api",
        "graph.facebook",
        "token",
        "localhost",
    )

    if any(marker in lowered for marker in technical_markers):
        return INSTAGRAM_LIVE_CONNECTION_MESSAGE

    return text


def _suggestion_payload(item):
    display = parse_suggestion_display(item.content_text)
    poster_url = None

    if item.poster:
        try:
            poster_url = item.poster.url
        except ValueError:
            poster_url = None

    return {
        "id": item.id,
        "title": item.title,
        "content": item.content_text,
        "display": display,
        "poster_url": poster_url,
        "platform": item.platform,
        "is_selected": item.is_selected,
        "is_published": item.is_published,
        "instagram_permalink": item.instagram_permalink,
        "publish_error": _safe_instagram_publish_error(
            item.publish_error
        ),
    }


def _document_rag_states(documents):
    document_list = list(documents)
    counts = {}

    try:
        counts = VectorStore().document_chunk_counts(
            [document.id for document in document_list]
        )
    except Exception:
        return {
            document.id: {
                "state": "unavailable",
                "label": "Indexing unavailable",
                "chunks": 0,
            }
            for document in document_list
        }

    states = {}

    for document in document_list:
        chunk_count = counts.get(document.id, 0)
        if chunk_count > 0:
            states[document.id] = {
                "state": "indexed",
                "label": "Indexed",
                "chunks": chunk_count,
            }
        else:
            states[document.id] = {
                "state": "not_indexed",
                "label": "Not Indexed",
                "chunks": 0,
            }

    return states


def _ingest_knowledge_document(document):
    try:
        chunk_count = DocumentIngestionService().process_document(
            document
        )
        return chunk_count, None
    except Exception as exc:
        return None, str(exc)

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
    active_campaigns_count = owned_campaigns.filter(
        status="Active"
    ).count()

    ai_contents_count = CampaignContent.objects.filter(
        campaign__company__owner=request.user,
        ai_generated=True
    ).count()

    conversations_count = SupportConversation.objects.filter(
        company__owner=request.user
    ).count()

    recent_campaigns = owned_campaigns.order_by(
        "-created_at"
    )[:5]

    recent_ai_content = (
        CampaignContent.objects.filter(
            campaign__company__owner=request.user,
            ai_generated=True,
            poster__isnull=False,
        )
        .exclude(poster="")
        .select_related("campaign", "campaign__company")
        .order_by("-created_at")[:6]
    )

    recent_support_messages = (
        SupportMessage.objects.filter(
            conversation__company__owner=request.user
        )
        .select_related("conversation", "conversation__company")
        .order_by("-created_at")[:5]
    )

    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")

    return render(
        request,
        "dashboard/home.html",
        {
            "companies_count": companies_count,
            "products_count": products_count,
            "campaigns_count": campaigns_count,
            "active_campaigns_count": active_campaigns_count,
            "ai_contents_count": ai_contents_count,
            "conversations_count": conversations_count,
            "recent_campaigns": recent_campaigns,
            "recent_ai_content": recent_ai_content,
            "recent_support_messages": recent_support_messages,
            "companies": companies,
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
def company_workspace(request, company_id):
    context = workspace_context(
        request,
        company_id,
        tab="overview",
    )
    company = context["workspace_company"]

    context.update(
        {
            "products_count": Product.objects.filter(
                company=company
            ).count(),
            "campaigns_count": Campaign.objects.filter(
                company=company
            ).count(),
            "documents_count": KnowledgeDocument.objects.filter(
                company=company
            ).count(),
            "conversations_count": SupportConversation.objects.filter(
                company=company
            ).count(),
        }
    )

    return render(
        request,
        "dashboard/company_workspace.html",
        context,
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

            return redirect_company_scope(
                request,
                "companies_dashboard",
                "company_workspace",
            )

    else:

        form = CompanyForm(
            instance=company
        )

    context = workspace_context(
        request,
        workspace_id_from_request(request),
        tab="overview",
    )
    context.update(
        {
            "form": form,
            "company": company,
            "page_title": "Edit Company",
            "button_text": "Save Changes",
        }
    )

    return render(
        request,
        "dashboard/company_form.html",
        context,
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
def products_dashboard(request, company_id=None):

    products = Product.objects.filter(
        company__owner=request.user
    ).select_related(
        "company"
    ).order_by(
        "-created_at"
    )

    context = workspace_context(
        request,
        company_id,
        tab="products" if company_id else None,
    )
    workspace_company = context["workspace_company"]

    if workspace_company:
        products = products.filter(company=workspace_company)

    context["products"] = products

    return render(
        request,
        "dashboard/products.html",
        context,
    )


@marketing_specialist_required
def product_create(request):

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="products" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = ProductForm(
            request.POST,
            request.FILES,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Product added successfully."
            )

            return redirect_company_scope(
                request,
                "products_dashboard",
                "company_products_dashboard",
            )

    else:

        form = ProductForm(
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "page_title": "Add Product",
            "button_text": "Add Product",
        }
    )

    return render(
        request,
        "dashboard/product_form.html",
        workspace,
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

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="products" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = ProductForm(
            request.POST,
            request.FILES,
            instance=product,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Product updated successfully."
            )

            return redirect_company_scope(
                request,
                "products_dashboard",
                "company_products_dashboard",
            )

    else:

        form = ProductForm(
            instance=product,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "product": product,
            "page_title": "Edit Product",
            "button_text": "Save Changes",
        }
    )

    return render(
        request,
        "dashboard/product_form.html",
        workspace,
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

    return redirect_company_scope(
        request,
        "products_dashboard",
        "company_products_dashboard",
    )
    
# ==========================================================
# CAMPAIGN MANAGEMENT
# ==========================================================

@marketing_specialist_required
def campaigns_dashboard(request, company_id=None):

    campaigns = Campaign.objects.filter(
        company__owner=request.user
    ).select_related(
        "company",
        "product"
    ).order_by(
        "-created_at"
    )

    context = workspace_context(
        request,
        company_id,
        tab="campaigns" if company_id else None,
    )
    workspace_company = context["workspace_company"]

    if workspace_company:
        campaigns = campaigns.filter(company=workspace_company)

    context["campaigns"] = campaigns

    return render(
        request,
        "dashboard/campaigns.html",
        context,
    )


@marketing_specialist_required
def campaign_create(request):

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="campaigns" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = CampaignForm(
            request.POST,
            user=request.user
        )

        if workspace_company:
            limit_campaign_form_to_company(form, workspace_company)

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

                    return redirect_company_scope(
                        request,
                        "campaigns_dashboard",
                        "company_campaigns_dashboard",
                    )

    else:

        form = CampaignForm(
            user=request.user
        )

        if workspace_company:
            limit_campaign_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "page_title": "Add Campaign",
            "button_text": "Add Campaign",
        }
    )

    return render(
        request,
        "dashboard/campaign_form.html",
        workspace,
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

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="campaigns" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = CampaignForm(
            request.POST,
            instance=campaign,
            user=request.user
        )

        if workspace_company:
            limit_campaign_form_to_company(form, workspace_company)

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

                return redirect_company_scope(
                    request,
                    "campaigns_dashboard",
                    "company_campaigns_dashboard",
                )

    else:

        form = CampaignForm(
            instance=campaign,
            user=request.user
        )

        if workspace_company:
            limit_campaign_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "campaign": campaign,
            "page_title": "Edit Campaign",
            "button_text": "Save Changes",
        }
    )

    return render(
        request,
        "dashboard/campaign_form.html",
        workspace,
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

    return redirect_company_scope(
        request,
        "campaigns_dashboard",
        "company_campaigns_dashboard",
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

    advisor_result = None
    advisor_error = None

    if (
        request.method == "POST"
        and request.POST.get("action") == "generate_ai_recommendations"
    ):
        try:
            advisor_result = CampaignAdvisor().generate(
                campaign,
                result.get("summary") or {},
            )
        except Exception:
            advisor_error = (
                "AI recommendations could not be generated. "
                "Campaign analytics are still available."
            )

    return render(
        request,
        "dashboard/campaign_analytics.html",
        {
            "campaign": campaign,
            "analytics": result,
            "advisor_result": advisor_result,
            "advisor_error": advisor_error,
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
def ai_content_dashboard(request, company_id=None):

    campaigns = (
        Campaign.objects
        .filter(company__owner=request.user)
        .select_related("company", "product")
        .order_by("-created_at")
    )

    workspace = workspace_context(
        request,
        company_id,
        tab="ai_content" if company_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if workspace_company:
        campaigns = campaigns.filter(company=workspace_company)

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
                                _suggestion_payload(item)
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

            elif not _instagram_is_configured():
                messages.info(
                    request,
                    INSTAGRAM_LIVE_CONNECTION_MESSAGE
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

                except InstagramConfigError:
                    messages.info(
                        request,
                        INSTAGRAM_LIVE_CONNECTION_MESSAGE
                    )

                except InstagramPublishError as publish_error:
                    messages.error(
                        request,
                        _safe_instagram_publish_error(publish_error)
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
                _suggestion_payload(item)
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
            "instagram_configured": _instagram_is_configured(),
            **workspace,
        }
    )
    

# ==========================================================
# CUSTOMER SUPPORT
# ==========================================================
    
@marketing_specialist_required
def customer_support_dashboard(request, company_id=None):

    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")

    selected_company = None
    conversations = []
    support_analytics = None
    error = None

    selected_id = company_id or request.GET.get("company")

    workspace = workspace_context(
        request,
        company_id,
        tab="support" if company_id else None,
    )

    if selected_id:

        selected_company = get_object_or_404(
            Company,
            id=selected_id,
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

    knowledge_count = 0
    conversation_count = 0
    rag_indexed = False

    if selected_company:
        knowledge_count = KnowledgeDocument.objects.filter(
            company=selected_company
        ).count()
        conversation_count = len(conversations)
        try:
            rag_indexed = VectorStore().company_has_chunks(
                selected_company.id
            )
        except Exception:
            rag_indexed = False

    return render(
        request,
        "dashboard/customer_support.html",
        {
            "companies": companies,
            "selected_company": selected_company,
            "conversations": conversations,
            "support_analytics": support_analytics,
            "error": error,
            "knowledge_count": knowledge_count,
            "conversation_count": conversation_count,
            "rag_indexed": rag_indexed,
            **workspace,
        }
    )
    
    
# ==========================================================
# REPORT GENERATION
# ==========================================================
    
@marketing_specialist_required
def reports_dashboard(request, company_id=None):

    campaigns = Campaign.objects.filter(
        company__owner=request.user
    ).select_related(
        "company",
        "product"
    ).order_by(
        "-created_at"
    )

    workspace = workspace_context(
        request,
        company_id,
        tab="reports" if company_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if workspace_company:
        campaigns = campaigns.filter(company=workspace_company)

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

        if (
            workspace_company
            and selected_campaign.company_id != workspace_company.id
        ):
            raise Http404()

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
            **workspace,
        }
    )
    # ==========================================================
# KNOWLEDGE BASE
# ==========================================================

@marketing_specialist_required
def knowledge_base_dashboard(request, company_id=None):

    documents = KnowledgeDocument.objects.filter(
        company__owner=request.user
    ).select_related(
        "company"
    ).order_by(
        "-uploaded_at"
    )

    context = workspace_context(
        request,
        company_id,
        tab="knowledge" if company_id else None,
    )
    workspace_company = context["workspace_company"]

    if workspace_company:
        documents = documents.filter(company=workspace_company)

    documents = list(documents)
    rag_states = _document_rag_states(documents)

    for document in documents:
        document.rag_state = rag_states.get(document.id, {
            "state": "unavailable",
            "label": "Indexing unavailable",
            "chunks": 0,
        })

    context["documents"] = documents

    return render(
        request,
        "dashboard/knowledge_base.html",
        context,
    )


@marketing_specialist_required
def knowledge_document_create(request):

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="knowledge" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = KnowledgeDocumentForm(
            request.POST,
            request.FILES,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

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

                chunk_count, ingest_error = (
                    _ingest_knowledge_document(document)
                )

                if ingest_error:
                    messages.warning(
                        request,
                        "Document saved, but AI indexing failed."
                    )
                elif not chunk_count:
                    messages.warning(
                        request,
                        "Document saved, but AI indexing failed."
                    )
                else:
                    messages.success(
                        request,
                        "Document successfully indexed for AI retrieval."
                    )

                return redirect_company_scope(
                    request,
                    "knowledge_base_dashboard",
                    "company_knowledge_dashboard",
                )

    else:

        form = KnowledgeDocumentForm(
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "page_title": "Add Knowledge Document",
            "button_text": "Upload Document",
        }
    )

    return render(
        request,
        "dashboard/knowledge_form.html",
        workspace,
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

    workspace_id = workspace_id_from_request(request)
    workspace = workspace_context(
        request,
        workspace_id,
        tab="knowledge" if workspace_id else None,
    )
    workspace_company = workspace["workspace_company"]

    if request.method == "POST":

        form = KnowledgeDocumentForm(
            request.POST,
            request.FILES,
            instance=document,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

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

                chunk_count, ingest_error = (
                    _ingest_knowledge_document(updated_document)
                )

                if ingest_error:
                    messages.warning(
                        request,
                        "Document saved, but AI indexing failed."
                    )
                elif not chunk_count:
                    messages.warning(
                        request,
                        "Document saved, but AI indexing failed."
                    )
                else:
                    messages.success(
                        request,
                        "Document successfully indexed for AI retrieval."
                    )

                return redirect_company_scope(
                    request,
                    "knowledge_base_dashboard",
                    "company_knowledge_dashboard",
                )

    else:

        form = KnowledgeDocumentForm(
            instance=document,
            user=request.user
        )

        if workspace_company:
            limit_form_to_company(form, workspace_company)

    workspace.update(
        {
            "form": form,
            "document": document,
            "page_title": "Edit Knowledge Document",
            "button_text": "Save Changes",
        }
    )

    return render(
        request,
        "dashboard/knowledge_form.html",
        workspace,
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

    return redirect_company_scope(
        request,
        "knowledge_base_dashboard",
        "company_knowledge_dashboard",
    )