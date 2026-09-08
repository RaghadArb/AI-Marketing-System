from ai_services.services.content_generator import ContentGenerator

from .models import CampaignContent


# Frozen: admin/API generation is retired.
# The live pipeline is dashboard.ai_content_dashboard
# (Creative Brief → ContentGenerator → 3 suggestions → posters).
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

        validation_errors = []


        for language in languages:

            result = self.generator.generate_campaign_content(
                campaign=campaign,
                language=language
            )


            content = result.get(
                "content",
                ""
            )

            validation = result.get(
                "validation",
                {}
            )

            is_valid = validation.get(
                "is_valid",
                False
            )

            errors = validation.get(
                "errors",
                []
            )


            # Do not save invalid AI content
            if not is_valid:

                validation_errors.append({
                    "language": language,
                    "errors": errors
                })

                print(
                    f"AI content rejected for "
                    f"{language}: {errors}"
                )

                continue


            # Save only validated content
            campaign_content = CampaignContent.objects.create(
                campaign=campaign,
                title=f"{campaign.campaign_name} - {language}",
                content_text=content,
                content_type="Post",
                platform=campaign.platform,
                language=language,
                ai_generated=True,
                is_selected=False,
                is_published=False
            )


            generated_contents.append(
                campaign_content
            )


        return {
            "contents": generated_contents,
            "validation_errors": validation_errors
        }