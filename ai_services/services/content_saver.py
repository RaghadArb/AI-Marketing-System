from campaign.models import CampaignContent


class ContentSaver:

    def save(
        self,
        campaign,
        content,
        platform,
        content_type="Post"
    ):

        campaign_content = CampaignContent.objects.create(
            campaign=campaign,
            title="AI Generated Content",
            content_text=content,
            content_type=content_type,
            platform=platform,
            ai_generated=True
        )

        return campaign_content