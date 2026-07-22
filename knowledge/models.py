from django.db import models
from companies.models import Company


class KnowledgeDocument(models.Model):

    DOCUMENT_TYPES = [
        ('PDF', 'PDF'),
        ('DOCX', 'DOCX'),
        ('TXT', 'TXT'),
        ('Other', 'Other'),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='documents'
    )

    title = models.CharField(
        max_length=150
    )

    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPES,
        default='PDF'
    )

    file = models.FileField(
        upload_to='knowledge_documents/'
    )

    description = models.TextField(
        blank=True
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return self.title