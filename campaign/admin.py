from django.contrib import admin
from .models import Campaign, CampaignContent, CampaignPerformance

admin.site.register(Campaign)
admin.site.register(CampaignContent)
admin.site.register(CampaignPerformance)