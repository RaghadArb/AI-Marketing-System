from django.shortcuts import get_object_or_404, redirect

from companies.models import Company
from products.models import Product


def owned_company(request, company_id):
    return get_object_or_404(
        Company,
        id=company_id,
        owner=request.user,
    )


def workspace_id_from_request(request):
    raw = request.POST.get("workspace") or request.GET.get("workspace")

    if not raw:
        return None

    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def workspace_context(request, company_id=None, tab=None):
    companies = Company.objects.filter(
        owner=request.user
    ).order_by("company_name")

    company = None

    if company_id:
        company = owned_company(request, company_id)

    return {
        "workspace_company": company,
        "workspace_tab": tab,
        "workspace_companies": companies,
    }


def redirect_company_scope(
    request,
    global_name,
    workspace_name,
    company=None,
):
    company_id = (
        company.id
        if company is not None
        else workspace_id_from_request(request)
    )

    if company_id:
        owned_company(request, company_id)
        return redirect(
            workspace_name,
            company_id=company_id,
        )

    return redirect(global_name)


def limit_form_to_company(form, company):
    if "company" not in form.fields:
        return form

    form.fields["company"].queryset = Company.objects.filter(
        id=company.id
    )
    form.initial.setdefault("company", company.id)
    form.fields["company"].initial = company.id
    return form


def limit_campaign_form_to_company(form, company):
    limit_form_to_company(form, company)

    if "product" in form.fields:
        form.fields["product"].queryset = Product.objects.filter(
            company=company
        )

    return form
