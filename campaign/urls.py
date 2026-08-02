from django.urls import path
from .views import generate_campaign_content
from .views import campaign_analytics

urlpatterns = [
    path(
        "generate-content/<int:campaign_id>/",
        generate_campaign_content,
        name="generate-content"
    ),
    path(
    "<int:campaign_id>/analytics/",
    campaign_analytics,
    name="campaign_analytics"
    ),
]