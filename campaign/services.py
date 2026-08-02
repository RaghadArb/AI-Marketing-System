from ai_services.services.content_generator import ContentGenerator

from .models import CampaignContent

# responsible for the business logic

class CampaignAIService:


    def __init__(self):

        self.generator = ContentGenerator()



    def generate_campaign_contents(
        self,
        campaign
    ):

        languages = [
            "Arabic",
            "English"
        ]

        generated_contents = []


        for language in languages:

            content = self.generator.generate_campaign_content(
                campaign=campaign,
                language=language
            )


            campaign_content = CampaignContent.objects.create(
                campaign=campaign,
                title=f"{campaign.campaign_name} - {language}",
                content_text=content,
                content_type="Post",
                platform=campaign.platform,
                language=language,
                ai_generated=True
            )


            generated_contents.append(
                campaign_content
            )


        return generated_contents