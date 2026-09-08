from django import forms

from .models import Company


class CompanyForm(forms.ModelForm):

    class Meta:
        model = Company

        fields = [
            "company_name",
            "industry",
            "description",
            "website",
            "logo",
        ]

        widgets = {
            "company_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter company name",
                }
            ),

            "industry": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter company description",
                }
            ),

            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "https://example.com",
                }
            ),

            "logo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                }
            ),
        }