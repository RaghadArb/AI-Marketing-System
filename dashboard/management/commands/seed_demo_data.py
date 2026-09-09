from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from campaign.models import Campaign, CampaignContent, CampaignPerformance
from companies.models import Company
from customer_support.models import SupportConversation, SupportMessage
from knowledge.models import KnowledgeDocument
from products.models import Product


def _image_file(color, label, size=(640, 640), filename="demo.png"):
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle(
        [(24, 24), (size[0] - 24, size[1] - 24)],
        outline=(255, 255, 255),
        width=4,
    )
    draw.text(
        (40, size[1] // 2 - 10),
        label[:28],
        fill=(255, 255, 255),
        font=font,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return ContentFile(buffer.getvalue(), name=filename)


def _attach_image(field, color, label, filename):
    if field:
        return
    field.save(
        filename,
        _image_file(color, label, filename=filename),
        save=True,
    )


class Command(BaseCommand):
    help = (
        "Add demo companies, products, campaigns, AI content, "
        "analytics, knowledge documents, and support conversations "
        "for every Marketing Specialist."
    )

    def handle(self, *args, **options):
        specialists = User.objects.filter(
            profile__role="MARKETING_SPECIALIST"
        )

        if not specialists.exists():
            self.stderr.write(
                "No MARKETING_SPECIALIST user found. "
                "Create one before seeding demo data."
            )
            return

        for user in specialists:
            self._seed_for_user(user)

        self.stdout.write(
            self.style.SUCCESS(
                "Demo data is ready for the Marketing Specialist dashboard."
            )
        )

    def _seed_for_user(self, user):
        olive, _ = Company.objects.get_or_create(
            owner=user,
            company_name="Demo - Olive Grove Kitchen",
            defaults={
                "industry": "Restaurant",
                "description": (
                    "A modern Palestinian-Jordanian restaurant serving "
                    "fresh mezze, wood-fired dishes, and seasonal olive oil."
                ),
                "website": "https://olivegrove.example.com",
            },
        )
        _attach_image(
            olive.logo,
            (46, 125, 50),
            "Olive Grove",
            "demo_olive_logo.png",
        )

        aurora, _ = Company.objects.get_or_create(
            owner=user,
            company_name="Demo - Aurora Skin Lab",
            defaults={
                "industry": "Retail",
                "description": (
                    "A clean skincare brand focused on vitamin C serums "
                    "and daily SPF for Middle East climates."
                ),
                "website": "https://auroraskin.example.com",
            },
        )
        _attach_image(
            aurora.logo,
            (25, 118, 210),
            "Aurora Skin",
            "demo_aurora_logo.png",
        )

        zaatar, _ = Product.objects.get_or_create(
            company=olive,
            product_name="Demo - Zaatar Flatbread Box",
            defaults={
                "category": "Ready meals",
                "description": (
                    "A family box of wood-fired zaatar flatbread with "
                    "house-pressed olive oil and labneh."
                ),
                "price": Decimal("18.50"),
                "status": "Available",
            },
        )
        _attach_image(
            zaatar.product_image,
            (121, 85, 61),
            "Zaatar Box",
            "demo_zaatar.png",
        )

        oil, _ = Product.objects.get_or_create(
            company=olive,
            product_name="Demo - Extra Virgin Olive Oil",
            defaults={
                "category": "Pantry",
                "description": (
                    "Cold-pressed extra virgin olive oil from family groves. "
                    "Peppery finish, no additives."
                ),
                "price": Decimal("24.00"),
                "status": "Available",
            },
        )
        _attach_image(
            oil.product_image,
            (85, 107, 47),
            "Olive Oil",
            "demo_oil.png",
        )

        serum, _ = Product.objects.get_or_create(
            company=aurora,
            product_name="Demo - Glow Vitamin C Serum",
            defaults={
                "category": "Skincare",
                "description": (
                    "A lightweight 10% vitamin C serum for morning glow. "
                    "Fragrance-free and suitable for daily use."
                ),
                "price": Decimal("39.90"),
                "status": "Available",
            },
        )
        _attach_image(
            serum.product_image,
            (255, 160, 80),
            "Vitamin C",
            "demo_serum.png",
        )

        ramadan, _ = Campaign.objects.get_or_create(
            company=olive,
            campaign_name="Demo - Ramadan Family Table",
            defaults={
                "product": zaatar,
                "objective": (
                    "Increase Iftar family-box orders on Instagram "
                    "during Ramadan with warm, home-style creative."
                ),
                "platform": "Instagram",
                "budget": Decimal("1200.00"),
                "start_date": timezone.now().date() - timedelta(days=21),
                "end_date": timezone.now().date() + timedelta(days=10),
                "status": "Active",
            },
        )
        launch, _ = Campaign.objects.get_or_create(
            company=aurora,
            campaign_name="Demo - Summer Glow Launch",
            defaults={
                "product": serum,
                "objective": (
                    "Drive awareness and product-page clicks for the "
                    "new vitamin C serum among young professionals."
                ),
                "platform": "Instagram",
                "budget": Decimal("2500.00"),
                "start_date": timezone.now().date() - timedelta(days=14),
                "end_date": timezone.now().date() + timedelta(days=21),
                "status": "Active",
            },
        )
        pantry, _ = Campaign.objects.get_or_create(
            company=olive,
            campaign_name="Demo - Olive Oil Gift Season",
            defaults={
                "product": oil,
                "objective": (
                    "Promote gift bottles of extra virgin olive oil "
                    "for family gatherings and corporate gifting."
                ),
                "platform": "Facebook",
                "budget": Decimal("800.00"),
                "start_date": timezone.now().date() - timedelta(days=40),
                "end_date": timezone.now().date() - timedelta(days=5),
                "status": "Completed",
            },
        )

        self._seed_performance(ramadan)
        self._seed_performance(launch)
        self._seed_performance(pantry)
        self._seed_content(ramadan, "Iftar")
        self._seed_content(launch, "Glow")
        self._seed_knowledge(olive, aurora)
        self._seed_support(olive)

        self.stdout.write(
            f"Seeded demo records for {user.username}."
        )

    def _seed_performance(self, campaign):
        if campaign.performance.exists():
            return

        rows = [
            ("Instagram", 18400, 920, 1460, 210, 95),
            ("Instagram", 22100, 1180, 1890, 260, 140),
            ("Facebook", 9800, 410, 520, 80, 44),
            ("TikTok", 31200, 1560, 2400, 390, 210),
        ]
        now = timezone.now()

        for index, (
            platform,
            views,
            clicks,
            likes,
            shares,
            comments,
        ) in enumerate(rows):
            record = CampaignPerformance.objects.create(
                campaign=campaign,
                platform=platform,
                views=views,
                clicks=clicks,
                likes=likes,
                shares=shares,
                comments=comments,
                language="Arabic",
            )
            CampaignPerformance.objects.filter(id=record.id).update(
                recorded_at=now - timedelta(days=12 - index * 3)
            )

    def _seed_content(self, campaign, theme):
        if campaign.contents.filter(title__startswith="Demo -").exists():
            return

        suggestions = [
            (
                f"Demo - {theme} suggestion 1",
                (
                    f"Suggestion 1\n\n"
                    f"Title: {theme} starts at the table\n\n"
                    "Caption: Gather the people you love. Fresh flavors, "
                    "warm light, and a simple invitation to share the meal.\n\n"
                    "Hashtags: #DemoCampaign #FamilyTable #MadeLocal\n\n"
                    "Call to Action: Order your family box today"
                ),
                True,
            ),
            (
                f"Demo - {theme} suggestion 2",
                (
                    f"Suggestion 2\n\n"
                    f"Title: A brighter everyday ritual\n\n"
                    "Caption: Small habits, visible results. Built for busy "
                    "mornings and honest product claims only.\n\n"
                    "Hashtags: #DemoCampaign #DailyGlow #CleanRoutine\n\n"
                    "Call to Action: Shop the featured product"
                ),
                False,
            ),
            (
                f"Demo - {theme} suggestion 3",
                (
                    f"Suggestion 3\n\n"
                    f"Title: Made to be shared\n\n"
                    "Caption: A gift that feels personal: quality ingredients, "
                    "clear sourcing, and a story your audience can trust.\n\n"
                    "Hashtags: #DemoCampaign #ShareTheTable #LocalBrand\n\n"
                    "Call to Action: Send it as a gift"
                ),
                False,
            ),
        ]

        for title, text, selected in suggestions:
            item = CampaignContent.objects.create(
                campaign=campaign,
                title=title,
                content_text=text,
                content_type="Post",
                platform=campaign.platform,
                language="English",
                ai_generated=True,
                is_selected=selected,
                is_published=False,
            )
            _attach_image(
                item.poster,
                (23, 37, 84) if selected else (90, 90, 90),
                title.replace("Demo - ", ""),
                f"demo_poster_{item.id}.png",
            )

    def _seed_knowledge(self, olive, aurora):
        docs = [
            (
                olive,
                "Demo - Olive Grove brand facts",
                (
                    "Olive Grove Kitchen is a restaurant brand. "
                    "Signature items: zaatar flatbread, labneh, and "
                    "extra virgin olive oil. We do not invent discounts. "
                    "Opening hours: 12:00 to 23:00. Delivery is available "
                    "inside Amman. No unverified certifications."
                ),
            ),
            (
                aurora,
                "Demo - Aurora Skin Lab product facts",
                (
                    "Aurora Skin Lab Glow Vitamin C Serum contains 10% "
                    "vitamin C. Fragrance-free. For morning use under SPF. "
                    "Do not claim medical results or invented clinical "
                    "percentages. Suitable for daily cosmetic use."
                ),
            ),
        ]

        for company, title, body in docs:
            if KnowledgeDocument.objects.filter(
                company=company,
                title=title,
            ).exists():
                continue

            document = KnowledgeDocument(
                company=company,
                title=title,
                document_type="TXT",
                description="Demo knowledge used to ground AI copy.",
            )
            document.file.save(
                f"demo_{company.id}.txt",
                ContentFile(body.encode("utf-8")),
                save=True,
            )

    def _seed_support(self, company):
        if company.support_conversations.exists():
            return

        conversation = SupportConversation.objects.create(
            company=company
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender="Customer",
            message_text=(
                "Do you deliver the zaatar family box the same evening?"
            ),
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender="AI",
            message_text=(
                "Yes, Olive Grove Kitchen offers delivery inside Amman. "
                "Place the family box order before 18:00 for same-evening "
                "delivery when kitchen capacity allows."
            ),
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender="Customer",
            message_text="Is the olive oil extra virgin?",
        )
        SupportMessage.objects.create(
            conversation=conversation,
            sender="AI",
            message_text=(
                "Yes. The featured oil is cold-pressed extra virgin olive oil "
                "with no additives."
            ),
        )

        second = SupportConversation.objects.create(company=company)
        SupportMessage.objects.create(
            conversation=second,
            sender="Customer",
            message_text="What are your opening hours?",
        )
        SupportMessage.objects.create(
            conversation=second,
            sender="AI",
            message_text="We are open from 12:00 to 23:00.",
        )
