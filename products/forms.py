from django import forms

from .models import Product


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product

        fields = [
            "company",
            "product_name",
            "category",
            "description",
            "price",
            "product_image",
            "status",
        ]

        widgets = {
            "company": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "product_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter product name",
                }
            ),

            "category": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter product category",
                }
            ),

            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter product description",
                }
            ),

            "price": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "product_image": forms.ClearableFileInput(
                attrs={
                    "class": "form-control"
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
                user.companies.all()
            )