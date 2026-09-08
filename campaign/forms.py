from django import forms

from .models import Campaign
from companies.models import Company
from products.models import Product


class CampaignForm(forms.ModelForm):

    class Meta:
        model = Campaign

        fields = [
            "company",
            "product",
            "campaign_name",
            "objective",
            "platform",
            "budget",
            "start_date",
            "end_date",
            "status",
        ]

        widgets = {
            "company": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "product": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "campaign_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter campaign name",
                }
            ),

            "objective": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter campaign objective",
                }
            ),

            "platform": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "budget": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "start_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "end_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "status": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),
        }


    def __init__(self, *args, user=None, **kwargs):

        super().__init__(*args, **kwargs)

        if user is not None:

            self.fields["company"].queryset = (
                Company.objects.filter(
                    owner=user
                )
            )

            self.fields["product"].queryset = (
                Product.objects.filter(
                    company__owner=user
                )
            )