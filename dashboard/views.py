import os
import re
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import (
    render,
    get_object_or_404,
    redirect,
)
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse

from campaign.models import Campaign, CampaignContent
from companies.models import Company
from companies.forms import CompanyForm
from campaign.forms import CampaignForm

from ai_services.analytics.intelligence import CampaignIntelligence
from ai_services.analytics.service import AnalyticsService
from ai_services.services.customer_voice_analyzer import CustomerVoiceAnalyzer
from ai_services.rag.ingestion import DocumentIngestionService
from ai_services.rag.vector_store import VectorStore
from ai_services.services.campaign_advisor import CampaignAdvisor
from ai_services.services.content_generator import ContentGenerator
from ai_services.services.instagram_publisher import (
    InstagramConfigError,
    InstagramPublishError,
    InstagramPublisher,
)
from ai_services.services.marketing_strategy_agent import (
    MarketingStrategyAgent,
    StrategyGenerationError,
)
from ai_services.services.social_performance_importer import (
    SocialPerformanceImporter,
)
from ai_services.services.poster_generator import (
    POSTER_MODERATION_USER_MESSAGE,
    PosterGenerator,
    PosterModerationRejected,
    PosterProviderFallbackError,
)

from .decorators import marketing_specialist_required
from .presentation import parse_suggestion_display
from .strategy_store import (
    UNMAPPED_CAMPAIGN_FIELDS,
    brief_from_strategy,
    campaign_name_from_strategy,
    company_brief,
    load_campaign_strategy,
    load_creative_brief,
    load_draft,
    map_platform,
    product_brief,
    remember_workflow_campaign,
    save_campaign_strategy,
    save_creative_brief,
    save_draft,
    strategy_context_for_advisor,
    strategy_from_post,
    workflow_campaign_id,
)
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


logger = logging.getLogger(__name__)

POSTER_LIMIT_USER_MESSAGE = (
    "Image generation limit reached. We couldn’t generate the posters "
    "right now. Please try again later."
)


def _is_image_limit_error(error):
    message = str(error).lower()
    return bool(
        re.search(r"\b(?:402|429)\b", message)
        or any(
            marker in message
            for marker in (
                "credit",
                "quota",
                "rate limit",
                "rate-limit",
                "too many requests",
                "payment required",
            )
        )
    )


def _poster_failure_user_message(error):
    if (
        isinstance(error, PosterProviderFallbackError)
        and _is_image_limit_error(error.primary_error)
        and _is_image_limit_error(error.fallback_error)
    ):
        return POSTER_LIMIT_USER_MESSAGE
    return "We couldn’t generate the posters right now. Please try again later."


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


def _redirect_named(name, args=None, fragment=""):
    url = reverse(name, args=args or [])
    if fragment:
        url = f"{url}#{fragment}"
    return HttpResponseRedirect(url)


def _advisor_session_key(campaign_id):
    return str(campaign_id)


def _store_advisor_session(request, campaign_id, result=None, error=None):
    stored = request.session.get("campaign_advisor_by_id") or {}
    stored[_advisor_session_key(campaign_id)] = {
        "result": result,
        "error": error,
    }
    request.session["campaign_advisor_by_id"] = stored
    request.session.modified = True


def _load_advisor_session(request, campaign_id):
    stored = request.session.get("campaign_advisor_by_id") or {}
    return stored.get(_advisor_session_key(campaign_id)) or {}


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
        logger.exception(
            "Knowledge document %s could not be indexed",
            getattr(document, "id", None),
        )
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
def analytics_hub(request, company_id=None):
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
        "dashboard/analytics_hub.html",
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

                    return _continue_to_content_studio(
                        request,
                        campaign,
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
            "button_text": "Save and generate",
        }
    )

    return render(
        request,
        "dashboard/campaign_form.html",
        workspace,
    )


def _safe_dashboard_next(next_url):
    path = str(next_url or "").strip()
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return None
    if path.startswith("/dashboard/"):
        return path
    return None


def _content_studio_url(request, campaign=None, stage="generate"):
    workspace_id = workspace_id_from_request(request)
    if workspace_id:
        path = reverse(
            "company_ai_content_dashboard",
            args=[workspace_id],
        )
    else:
        path = reverse("ai_content_dashboard")
    query = []
    if campaign is not None:
        query.append(f"campaign={campaign.id}")
    if stage in ("generate", "review"):
        query.append(f"stage={stage}")
    if query:
        return f"{path}?{'&'.join(query)}"
    return path


def _continue_to_content_studio(request, campaign):
    remember_workflow_campaign(request, campaign.id)
    next_url = _safe_dashboard_next(request.POST.get("next"))
    stage = "generate"
    if next_url and "stage=review" in next_url:
        stage = "review"
    if next_url and "ai-content" not in next_url:
        if "/campaigns/" in next_url and next_url.rstrip("/").endswith("edit"):
            return redirect(
                _content_studio_url(request, campaign, "generate")
            )
        return redirect(next_url)
    return redirect(_content_studio_url(request, campaign, stage))


def _latest_studio_suggestions(campaign):
    latest_contents = list(
        CampaignContent.objects.filter(
            campaign=campaign,
            ai_generated=True,
        ).order_by("-created_at")[:3]
    )
    latest_contents.reverse()
    return [_suggestion_payload(item) for item in latest_contents]


def _brief_from_post(post):
    return {
        "focus": post.get("creative_focus", "").strip(),
        "style": post.get("creative_style", "").strip(),
        "colors": post.get("creative_colors", "").strip(),
        "background": post.get("creative_background", "").strip(),
        "composition": post.get("creative_composition", "").strip(),
        "mood": post.get("creative_mood", "").strip(),
        "additional": post.get("creative_additional", "").strip(),
    }


def _parse_optional_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return False


def _owned_strategy_company_product(request, company_id, product_id):
    company = get_object_or_404(
        Company,
        id=company_id,
        owner=request.user,
    )
    product = None
    if product_id:
        product = get_object_or_404(
            Product,
            id=product_id,
            company__owner=request.user,
        )
        if product.company_id != company.id:
            return company, None, (
                "The selected product does not belong to the selected company."
            )
    return company, product, None


@marketing_specialist_required
def marketing_strategy_planner(request):
    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")

    products = (
        Product.objects
        .filter(company__owner=request.user)
        .select_related("company")
        .order_by("product_name")
    )

    form_values = {
        "company_id": request.GET.get("company") or "",
        "product_id": request.GET.get("product") or "",
        "marketing_goal": "",
        "target_audience": "",
        "budget": "",
        "start_date": "",
        "end_date": "",
        "preferred_platform": "",
        "additional_information": "",
    }
    strategy = None
    error = None
    unmapped_fields = UNMAPPED_CAMPAIGN_FIELDS

    if request.method != "POST":
        draft = load_draft(request)
        if draft:
            form_values.update(draft.get("form") or {})
            strategy = draft.get("strategy")
            if request.GET.get("company"):
                form_values["company_id"] = request.GET.get("company")

    if request.method == "POST":
        action = request.POST.get("action", "generate_strategy")
        form_values = {
            "company_id": request.POST.get("company_id", "").strip(),
            "product_id": request.POST.get("product_id", "").strip(),
            "marketing_goal": request.POST.get("marketing_goal", "").strip(),
            "target_audience": (
                request.POST.get("brief_target_audience")
                or request.POST.get("target_audience")
                or ""
            ).strip(),
            "budget": request.POST.get("budget", "").strip(),
            "start_date": request.POST.get("start_date", "").strip(),
            "end_date": request.POST.get("end_date", "").strip(),
            "preferred_platform": request.POST.get(
                "preferred_platform",
                "",
            ).strip(),
            "additional_information": request.POST.get(
                "additional_information",
                "",
            ).strip(),
        }

        if action in ("generate_strategy", "regenerate_strategy"):
            if not form_values["company_id"]:
                error = "Select a company before generating a strategy."
            elif not form_values["marketing_goal"]:
                error = "Describe the marketing goal before generating a strategy."
            elif not form_values["target_audience"]:
                error = "Describe the target audience before generating a strategy."
            else:
                company, product, product_error = _owned_strategy_company_product(
                    request,
                    form_values["company_id"],
                    form_values["product_id"],
                )
                if product_error:
                    error = product_error
                else:
                    start_date = _parse_optional_date(form_values["start_date"])
                    end_date = _parse_optional_date(form_values["end_date"])
                    if start_date is False or end_date is False:
                        error = "Use valid start and end dates."
                    elif start_date and end_date and end_date < start_date:
                        error = "The end date cannot be before the start date."
                    else:
                        duration = "Not provided"
                        if start_date and end_date:
                            duration = (
                                f"{start_date.isoformat()} to "
                                f"{end_date.isoformat()} "
                                f"({(end_date - start_date).days} days)"
                            )
                        elif start_date or end_date:
                            duration = (
                                (start_date or end_date).isoformat()
                            )

                        try:
                            strategy = MarketingStrategyAgent().generate(
                                {
                                    "company_information": company_brief(company),
                                    "product_information": product_brief(product),
                                    "marketing_goal": form_values["marketing_goal"],
                                    "target_audience": form_values["target_audience"],
                                    "budget": form_values["budget"] or "Not provided",
                                    "dates": duration,
                                    "preferred_platform": form_values[
                                        "preferred_platform"
                                    ],
                                    "additional_information": form_values[
                                        "additional_information"
                                    ],
                                }
                            )
                            if form_values["preferred_platform"] and not strategy.get(
                                "recommended_platform"
                            ):
                                strategy["recommended_platform"] = form_values[
                                    "preferred_platform"
                                ]
                            if not strategy.get("target_audience"):
                                strategy["target_audience"] = form_values[
                                    "target_audience"
                                ]
                            save_draft(
                                request,
                                {
                                    "form": form_values,
                                    "strategy": strategy,
                                },
                            )
                        except StrategyGenerationError as exc:
                            error = str(exc)
                            strategy = None
                        except Exception:
                            error = (
                                "The strategy could not be generated. "
                                "No campaign was created."
                            )
                            strategy = None

        elif action == "create_campaign_from_strategy":
            strategy = strategy_from_post(request.POST)
            if not form_values["company_id"]:
                error = "Select a company before creating a campaign."
            elif not strategy.get("campaign_objective"):
                error = (
                    "Review and keep a campaign objective before creating "
                    "the campaign."
                )
            else:
                company, product, product_error = _owned_strategy_company_product(
                    request,
                    form_values["company_id"],
                    form_values["product_id"],
                )
                if product_error:
                    error = product_error
                elif company.owner_id != request.user.id:
                    error = "You cannot create a campaign for this company."
                else:
                    start_date = _parse_optional_date(form_values["start_date"])
                    end_date = _parse_optional_date(form_values["end_date"])
                    if start_date is False or end_date is False:
                        error = "Use valid start and end dates."
                    elif start_date and end_date and end_date < start_date:
                        error = "The end date cannot be before the start date."
                    else:
                        budget_value = None
                        if form_values["budget"]:
                            try:
                                budget_value = Decimal(form_values["budget"])
                            except InvalidOperation:
                                error = "Enter a valid budget amount."

                        if not error:
                            campaign = Campaign.objects.create(
                                company=company,
                                product=product,
                                campaign_name=campaign_name_from_strategy(
                                    strategy,
                                    product,
                                ),
                                objective=strategy["campaign_objective"],
                                platform=map_platform(
                                    strategy.get("recommended_platform")
                                    or form_values["preferred_platform"]
                                ),
                                budget=budget_value,
                                start_date=start_date or None,
                                end_date=end_date or None,
                                status="Draft",
                            )
                            save_campaign_strategy(
                                request,
                                campaign.id,
                                {
                                    "form": form_values,
                                    "strategy": strategy,
                                },
                            )
                            content_url = reverse("ai_content_dashboard")
                            return redirect(
                                f"{content_url}?campaign={campaign.id}"
                            )

        else:
            error = "Choose Generate Strategy or Create Campaign from Strategy."

    return render(
        request,
        "dashboard/strategy_planner.html",
        {
            "companies": companies,
            "products": products,
            "form_values": form_values,
            "strategy": strategy,
            "error": error,
            "unmapped_fields": unmapped_fields,
            "platforms": [
                value for value, _label in Campaign._meta.get_field(
                    "platform"
                ).choices
            ],
            "workflow_campaign_id": workflow_campaign_id(request),
        },
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
    remember_workflow_campaign(request, campaign.id)

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

                return _continue_to_content_studio(
                    request,
                    updated_campaign,
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
            "button_text": "Save and generate",
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

    return redirect_company_scope(
        request,
        "campaigns_dashboard",
        "company_campaigns_dashboard",
    )


# ==========================================================
# CAMPAIGN ANALYTICS
# ==========================================================

def _social_session_get(request, bucket, campaign_id, default=None):
    stored = request.session.get(bucket) or {}
    return stored.get(str(campaign_id), default)


def _social_session_set(request, bucket, campaign_id, value):
    stored = request.session.get(bucket) or {}
    stored[str(campaign_id)] = value
    request.session[bucket] = stored
    request.session.modified = True


def _campaign_analytics_context(
    request,
    campaign,
    advisor_result=None,
    advisor_error=None,
    social_error=None,
):
    analytics_service = AnalyticsService()
    result = analytics_service.get_campaign_analytics(campaign)
    chart_files = []
    for chart in result["charts"]:
        chart_files.append(os.path.basename(chart))
    result["charts"] = chart_files

    importer = SocialPerformanceImporter()
    fetch_state = _social_session_get(
        request,
        "social_fetch_posts",
        campaign.id,
        {},
    ) or {}
    imported_ids = _social_session_get(
        request,
        "social_imported_ids",
        campaign.id,
        [],
    ) or []
    live_verified = bool(
        _social_session_get(
            request,
            "social_live_verified",
            campaign.id,
            False,
        )
    )
    notice = _social_session_get(
        request,
        "social_import_notice",
        campaign.id,
        "",
    ) or ""
    if notice:
        _social_session_set(
            request,
            "social_import_notice",
            campaign.id,
            "",
        )

    posts = fetch_state.get("posts") or []
    imported_keys = importer.already_imported_keys(campaign)
    for post in posts:
        platform_label = importer.display_platform(post.get("platform"))
        post_id = str(post.get("external_post_id") or "")
        post["already_imported"] = (platform_label, post_id) in imported_keys
        post["selection_value"] = (
            f"{str(post.get('platform') or '').lower()}:{post_id}"
        )

    performances = list(campaign.performance.all())
    intelligence_service = CampaignIntelligence()
    intelligence = intelligence_service.build(
        campaign,
        result.get("summary") or {},
        performances,
    )
    strategy = (load_campaign_strategy(request, campaign.id) or {}).get(
        "strategy"
    )
    strategy_outcome = intelligence_service.strategy_vs_outcome(
        strategy,
        result.get("summary") or {},
        intelligence.get("diagnosis") or {},
    )
    voice = CustomerVoiceAnalyzer().analyze(
        campaign.company,
        campaign=campaign,
        use_ai=False,
    )
    combined = intelligence_service.combined_context(campaign, voice)

    advisor_state = _load_advisor_session(request, campaign.id)
    if advisor_result is None:
        advisor_result = advisor_state.get("result")
    if advisor_error is None:
        advisor_error = advisor_state.get("error")

    return {
        "campaign": campaign,
        "analytics": result,
        "intelligence": intelligence,
        "strategy_outcome": strategy_outcome,
        "voice_context": combined,
        "advisor_result": advisor_result,
        "advisor_error": advisor_error,
        "social_posts": posts,
        "social_source": fetch_state.get("source"),
        "social_error": social_error or fetch_state.get("display_error"),
        "social_notice": notice,
        "social_platforms": fetch_state.get("platforms") or "both",
        "social_connection": importer.connection_status(
            live_verified=live_verified,
        ),
        "social_imported_count": len(imported_ids),
    }


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
    remember_workflow_campaign(request, campaign.id)

    advisor_result = None
    advisor_error = None
    social_error = None

    if request.method == "POST":
        action = request.POST.get("action")
        importer = SocialPerformanceImporter()

        if action == "fetch_social_posts":
            platforms = request.POST.get("social_platforms") or "both"
            result = importer.fetch_posts(platforms, campaign)
            fetch_state = {
                "source": result.get("source"),
                "posts": result.get("posts") or [],
                "platforms": platforms,
                "display_error": result.get("error"),
            }
            _social_session_set(
                request,
                "social_fetch_posts",
                campaign.id,
                fetch_state,
            )
            if result.get("source") == "live" and result.get("posts"):
                _social_session_set(
                    request,
                    "social_live_verified",
                    campaign.id,
                    True,
                )
            return _redirect_named(
                "campaign_analytics_dashboard",
                args=[campaign.id],
                fragment="social-performance",
            )

        if action == "import_social_performance":
            fetch_state = _social_session_get(
                request,
                "social_fetch_posts",
                campaign.id,
                {},
            ) or {}
            posts = fetch_state.get("posts") or []
            selected_ids = request.POST.getlist("social_post_id")
            already = _social_session_get(
                request,
                "social_imported_ids",
                campaign.id,
                [],
            ) or []
            outcome = importer.import_selected(
                campaign,
                posts,
                selected_ids,
            )
            if outcome.get("error"):
                social_error = outcome["error"]
            else:
                imported = list(already) + list(outcome.get("imported_ids") or [])
                _social_session_set(
                    request,
                    "social_imported_ids",
                    campaign.id,
                    imported,
                )
                count = outcome.get("imported") or 0
                notice = (
                    f"{count} social post"
                    f"{'s' if count != 1 else ''} "
                    "were imported into campaign performance."
                )
                if outcome.get("skipped_duplicate"):
                    notice += (
                        f" {outcome['skipped_duplicate']} selected post(s) "
                        "were skipped because they were already imported."
                    )
                _social_session_set(
                    request,
                    "social_import_notice",
                    campaign.id,
                    notice,
                )
                return _redirect_named(
                    "campaign_analytics_dashboard",
                    args=[campaign.id],
                    fragment="social-performance",
                )

        if action == "generate_ai_recommendations":
            analytics_preview = AnalyticsService().get_campaign_analytics(
                campaign
            )
            imported_ids = _social_session_get(
                request,
                "social_imported_ids",
                campaign.id,
                [],
            ) or []
            strategy = (
                load_campaign_strategy(request, campaign.id) or {}
            ).get("strategy")
            extra = strategy_context_for_advisor(strategy) or {}
            if imported_ids:
                extra["performance_source_note"] = (
                    "Some performance records were imported from "
                    "selected social posts. Do not infer conversions "
                    "or revenue from engagement."
                )
            performances = list(campaign.performance.all())
            intelligence = CampaignIntelligence().build(
                campaign,
                analytics_preview.get("summary") or {},
                performances,
            )
            voice = CustomerVoiceAnalyzer().analyze(
                campaign.company,
                campaign=campaign,
                use_ai=False,
            )
            voice_payload = None
            if not voice.get("empty"):
                voice_payload = {
                    "topics": voice.get("topics"),
                    "sentiment": voice.get("sentiment"),
                    "concerns": voice.get("concerns"),
                    "questions": voice.get("questions"),
                    "filtered_to_campaign_dates": voice.get(
                        "filtered_to_campaign_dates"
                    ),
                    "customer_message_count": voice.get(
                        "customer_message_count"
                    ),
                }
            try:
                advisor_result = CampaignAdvisor().generate(
                    campaign,
                    analytics_preview.get("summary") or {},
                    strategy_context=extra or None,
                    intelligence=intelligence,
                    customer_voice=voice_payload,
                )
                advisor_error = None
            except Exception:
                advisor_result = None
                advisor_error = (
                    "AI recommendations could not be generated. "
                    "Campaign analytics are still available."
                )
            _store_advisor_session(
                request,
                campaign.id,
                result=advisor_result,
                error=advisor_error,
            )
            return _redirect_named(
                "campaign_analytics_dashboard",
                args=[campaign.id],
                fragment="ai-recommendations",
            )

    return render(
        request,
        "dashboard/campaign_analytics.html",
        _campaign_analytics_context(
            request,
            campaign,
            advisor_result=advisor_result,
            advisor_error=advisor_error,
            social_error=social_error,
        ),
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

    if request.method == "GET":
        query_campaign = request.GET.get("campaign")
        session_campaign = workflow_campaign_id(request)
        campaign_id = query_campaign or session_campaign
        if campaign_id:
            if query_campaign:
                selected_campaign = get_object_or_404(
                    Campaign,
                    id=campaign_id,
                    company__owner=request.user,
                )
            else:
                selected_campaign = campaigns.filter(id=campaign_id).first()
            if selected_campaign:
                remember_workflow_campaign(request, selected_campaign.id)
                saved_brief = load_creative_brief(
                    request,
                    selected_campaign.id,
                )
                stored = load_campaign_strategy(
                    request,
                    selected_campaign.id,
                )
                if saved_brief:
                    creative_brief = saved_brief
                elif stored and stored.get("strategy"):
                    creative_brief = brief_from_strategy(stored["strategy"])
                generated_suggestions = _latest_studio_suggestions(
                    selected_campaign
                )

    if request.method == "POST":

        action = request.POST.get("action", "generate")

        if action == "save_studio_state":
            campaign_id = request.POST.get("campaign_id")
            creative_brief = _brief_from_post(request.POST)
            if campaign_id:
                selected_campaign = get_object_or_404(
                    Campaign,
                    id=campaign_id,
                    company__owner=request.user,
                )
                save_creative_brief(
                    request,
                    selected_campaign.id,
                    creative_brief,
                )
                generated_suggestions = _latest_studio_suggestions(
                    selected_campaign
                )
            next_url = _safe_dashboard_next(request.POST.get("next"))
            if next_url:
                return redirect(next_url)
            if selected_campaign:
                return redirect(
                    _content_studio_url(
                        request,
                        selected_campaign,
                        "generate",
                    )
                )
            return redirect("ai_content_dashboard")

        if action == "generate":

            campaign_id = request.POST.get("campaign_id")

            creative_brief = _brief_from_post(request.POST)

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
                save_creative_brief(
                    request,
                    selected_campaign.id,
                    creative_brief,
                )
                remember_workflow_campaign(request, selected_campaign.id)

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
                                        variation_index=index,
                                    )
                                    saved_content.refresh_from_db()

                                except PosterModerationRejected:
                                    poster_failures.append(
                                        POSTER_MODERATION_USER_MESSAGE
                                    )
                                except Exception as poster_error:
                                    logger.exception(
                                        "Poster generation failed for suggestion %s "
                                        "in campaign %s",
                                        index,
                                        selected_campaign.id,
                                    )
                                    poster_failures.append(
                                        _poster_failure_user_message(
                                            poster_error
                                        )
                                    )

                                created_contents.append(
                                    saved_content
                                )

                            generated_suggestions = [
                                _suggestion_payload(item)
                                for item in created_contents
                            ]

                            if poster_failures:
                                unique_failures = list(
                                    dict.fromkeys(poster_failures)
                                )
                                if unique_failures == [
                                    POSTER_MODERATION_USER_MESSAGE
                                ]:
                                    error = POSTER_MODERATION_USER_MESSAGE
                                else:
                                    error = " ".join(unique_failures)
                                messages.error(request, error)

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
            remember_workflow_campaign(request, selected_campaign.id)
            saved_brief = load_creative_brief(
                request,
                selected_campaign.id,
            )
            if saved_brief:
                creative_brief = saved_brief
            generated_suggestions = _latest_studio_suggestions(
                selected_campaign
            )

    requested_stage = (
        request.GET.get("stage")
        or request.POST.get("stage")
        or ""
    ).strip()
    if requested_stage not in ("generate", "review"):
        requested_stage = None

    if (
        request.method == "POST"
        and generated_suggestions
        and request.POST.get("action", "generate") == "generate"
        and not error
    ):
        workflow_step = "review"
    elif requested_stage:
        workflow_step = requested_stage
    elif generated_suggestions:
        workflow_step = "review"
    else:
        workflow_step = "generate"

    studio_back_url = reverse("marketing_strategy_planner")
    studio_next_url = reverse("reports_dashboard")
    if selected_campaign:
        if workflow_step == "review":
            studio_back_url = _content_studio_url(
                request,
                selected_campaign,
                "generate",
            )
            studio_next_url = reverse(
                "campaign_analytics_dashboard",
                args=[selected_campaign.id],
            )
        else:
            studio_back_url = reverse(
                "campaign_edit",
                args=[selected_campaign.id],
            )
            studio_next_url = _content_studio_url(
                request,
                selected_campaign,
                "review",
            )

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
            "has_selected_content": any(
                item.get("is_selected")
                for item in generated_suggestions
            ),
            "studio_back_url": studio_back_url,
            "studio_next_url": studio_next_url,
            "workflow_step": workflow_step,
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
    error = None

    selected_id = (
        company_id
        or request.POST.get("company")
        or request.GET.get("company")
    )

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
            "error": error,
            "knowledge_count": knowledge_count,
            "conversation_count": conversation_count,
            "rag_indexed": rag_indexed,
            **workspace,
        }
    )


@marketing_specialist_required
def customer_support_analytics(request, company_id=None):
    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")
    selected_company = None
    selected_conversation = None
    conversations = []
    support_analytics = None
    customer_voice = None
    voice_error = None
    error = None

    selected_id = (
        company_id
        or request.POST.get("company")
        or request.GET.get("company")
    )
    conversation_id = (
        request.POST.get("conversation")
        or request.GET.get("conversation")
    )
    workspace = workspace_context(
        request,
        company_id,
        tab="support" if company_id else None,
    )
    if selected_id:
        selected_company = get_object_or_404(
            Company,
            id=selected_id,
            owner=request.user,
        )
        conversations = list(
            SupportConversation.objects
            .filter(company=selected_company)
            .prefetch_related("messages")
            .order_by("-started_at")
        )
        if conversation_id:
            selected_conversation = get_object_or_404(
                SupportConversation,
                id=conversation_id,
                company=selected_company,
            )
        try:
            support_analytics = AnalyticsService().get_support_analytics(
                selected_company
            )
        except Exception as exc:
            error = str(exc)
        use_ai = (
            request.method == "POST"
            and request.POST.get("action") == "analyze_customer_voice"
        )
        try:
            customer_voice = CustomerVoiceAnalyzer().analyze(
                selected_company,
                conversation=selected_conversation,
                use_ai=use_ai,
                include_knowledge_gaps=use_ai,
            )
        except Exception:
            if use_ai:
                voice_error = (
                    "Customer Voice analysis could not be completed. "
                    "Deterministic analytics are still available."
                )
                customer_voice = CustomerVoiceAnalyzer().analyze(
                    selected_company,
                    conversation=selected_conversation,
                    use_ai=False,
                )
            else:
                raise

    return render(
        request,
        "dashboard/customer_support_analytics.html",
        {
            "companies": companies,
            "selected_company": selected_company,
            "selected_conversation": selected_conversation,
            "conversations": conversations,
            "support_analytics": support_analytics,
            "customer_voice": customer_voice,
            "voice_error": voice_error,
            "error": error,
            **workspace,
        },
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

        remember_workflow_campaign(request, selected_campaign.id)

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

    return redirect_company_scope(
        request,
        "knowledge_base_dashboard",
        "company_knowledge_dashboard",
    )
