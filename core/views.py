from django.shortcuts import render

from campaign.models import Campaign, CampaignContent


def home(request):

    campaigns = Campaign.objects.all()

    contents = CampaignContent.objects.all().order_by(
        "-created_at"
    )

    context = {
        "campaigns": campaigns,
        "contents": contents,
    }

    return render(
        request,
        "dashboard.html",
        context
    )