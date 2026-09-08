from django import forms
from .models import KnowledgeDocument


class KnowledgeDocumentForm(forms.ModelForm):

    class Meta:
        model = KnowledgeDocument

        fields = [
            "company",
            "title",
            "document_type",
            "file",
            "description",
        ]

        widgets = {
            "company": forms.Select(
                attrs={"class": "form-select"}
            ),
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter document title",
                }
            ),
            "document_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "file": forms.ClearableFileInput(
                attrs={"class": "form-control"}
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter document description",
                }
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user is not None:
            self.fields["company"].queryset = (
                user.companies.all()
            )