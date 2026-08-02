from django.db import models
from companies.models import Company


class SupportConversation(models.Model):

    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='support_conversations'
    )


    started_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Conversation {self.id} - {self.company}"



class SupportMessage(models.Model):

    SENDER_CHOICES = [
        ('Customer', 'Customer'),
        ('AI', 'AI'),
    ]

    conversation = models.ForeignKey(
        SupportConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    sender = models.CharField(
        max_length=20,
        choices=SENDER_CHOICES
    )

    message_text = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True
    )


    def __str__(self):
        return f"{self.sender}: {self.message_text[:30]}"