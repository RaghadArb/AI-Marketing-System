from django.shortcuts import redirect


# Frozen obsolete endpoints.
# The live generation and analytics flows live in dashboard/views.py.
# URLs in campaign/urls.py are kept so existing links do not 404.


def generate_campaign_content(request, campaign_id):
    return redirect("ai_content_dashboard")


def campaign_analytics(request, campaign_id):
    return redirect(
        "campaign_analytics_dashboard",
        campaign_id=campaign_id,
    )
