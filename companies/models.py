from django.db import models
from django.contrib.auth.models import User


class Company(models.Model):

    INDUSTRY_CHOICES = [
        ('Restaurant', 'Restaurant'),
        ('Retail', 'Retail'),
        ('E-commerce', 'E-commerce'),
        ('Healthcare', 'Healthcare'),
        ('Education', 'Education'),
        ('Technology', 'Technology'),
        ('Other', 'Other'),
    ]
# each company has an owner and the owner can manage more than one company
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='companies',
        verbose_name='Marketing Manager'
    )

# the name of the company
    company_name = models.CharField(max_length=150)

# the type of the activity done by the company
    industry = models.CharField(
        max_length=30,
        choices=INDUSTRY_CHOICES,
        default='Other'
    )

# the description of the company
    description = models.TextField(blank=True)

# the website of the company
    website = models.URLField(blank=True)

# the logo of the company
    logo = models.ImageField(
        upload_to='company_logos/',
        blank=True,
        null=True
    )

# automatically take the date when the company is added
    created_at = models.DateTimeField(auto_now_add=True)

# automatically changes after any edit
    updated_at = models.DateTimeField(auto_now=True)

# so that the name of the company appears instead of the object
    def __str__(self):
        return self.company_name