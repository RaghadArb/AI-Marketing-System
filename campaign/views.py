from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Campaign
from ai_services.services.content_generator import ContentGenerator
from ai_services.services.content_saver import ContentSaver
from ai_services.analytics.service import AnalyticsService
from django.shortcuts import render


def generate_campaign_content(request, campaign_id):

    campaign = get_object_or_404(
        Campaign,
        id=campaign_id
    )

    agent = ContentGenerator()

    product_info = (
        campaign.product.product_name
        if campaign.product
        else "No product specified"
    )

    result = agent.generate(
        product=product_info,
        campaign=campaign.campaign_name,
        platform=campaign.platform,
        content_type="Post",
        language="Arabic",
        number_of_suggestions=3
    )
    saved_content = ContentSaver().save(
        campaign=campaign,
        content=result,
        platform=campaign.platform,
        content_type="Post"
    )

    return JsonResponse({
        "id": saved_content.id,
        "title": saved_content.title,
        "content": saved_content.content_text
    })
    
# to display the service of analytics on the dashboard
def campaign_analytics(request, campaign_id):

    campaign = get_object_or_404(
        Campaign,
        id=campaign_id
    )


    analytics_service = AnalyticsService()


    result = analytics_service.get_campaign_analytics(
        campaign
    )


    return render(
        request,
        "campaign/campaign_analytics.html",
        {
            "campaign": campaign,
            "analytics": result
        }
    )