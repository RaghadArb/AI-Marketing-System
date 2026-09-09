from django.db import models

from companies.models import Company
from products.models import Product


PLATFORM_CHOICES = [
    ("Instagram", "Instagram"),
    ("Facebook", "Facebook"),
    ("TikTok", "TikTok"),
    ("LinkedIn", "LinkedIn"),
    ("Google Ads", "Google Ads"),
    ("Email", "Email"),
    ("Other", "Other"),
]


class Campaign(models.Model):

    STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Active", "Active"),
        ("Completed", "Completed"),
        ("Paused", "Paused"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="campaigns"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="campaigns"
    )

    campaign_name = models.CharField(
        max_length=150
    )

    objective = models.TextField()

    platform = models.CharField(
        max_length=50,
        choices=PLATFORM_CHOICES
    )

    budget = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )

    start_date = models.DateField(
        null=True,
        blank=True
    )

    end_date = models.DateField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Draft"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.campaign_name


class CampaignContent(models.Model):

    CONTENT_TYPE_CHOICES = [
        ("Post", "Post"),
        ("Caption", "Caption"),
        ("Ad Copy", "Ad Copy"),
        ("Story", "Story"),
        ("Email", "Email"),
        ("Video Script", "Video Script"),
    ]

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="contents"
    )

    title = models.CharField(
        max_length=150
    )

    content_text = models.TextField()

    content_type = models.CharField(
        max_length=30,
        choices=CONTENT_TYPE_CHOICES,
        default="Post"
    )

    platform = models.CharField(
        max_length=50,
        choices=PLATFORM_CHOICES
    )

    language = models.CharField(
        max_length=20,
        choices=[
            ("Arabic", "Arabic"),
            ("English", "English"),
        ],
        default="Arabic"
    )

    poster = models.ImageField(
        upload_to="campaign_posters/",
        blank=True,
        null=True
    )

    ai_generated = models.BooleanField(
        default=True
    )

    is_selected = models.BooleanField(
        default=False
    )

    is_published = models.BooleanField(
        default=False
    )

    instagram_media_id = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    instagram_permalink = models.CharField(
        max_length=500,
        blank=True,
        default=""
    )

    published_at = models.DateTimeField(
        null=True,
        blank=True
    )

    publish_error = models.TextField(
        blank=True,
        default=""
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.title


class CampaignPerformance(models.Model):

    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="performance"
    )

    platform = models.CharField(
        max_length=50
    )

    views = models.PositiveIntegerField(
        default=0
    )

    clicks = models.PositiveIntegerField(
        default=0
    )

    likes = models.PositiveIntegerField(
        default=0
    )

    shares = models.PositiveIntegerField(
        default=0
    )

    comments = models.PositiveIntegerField(
        default=0
    )

    language = models.CharField(
        max_length=20,
        default="Arabic"
    )

    recorded_at = models.DateTimeField(
        auto_now_add=True
    )
