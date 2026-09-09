from django import template

from dashboard.presentation import campaign_progress_percent

register = template.Library()


@register.filter
def campaign_progress(campaign):
    return campaign_progress_percent(campaign)


@register.filter
def status_badge_class(status):
    mapping = {
        "Draft": "bg-secondary",
        "Active": "bg-success",
        "Completed": "bg-primary",
        "Paused": "bg-warning text-dark",
    }
    return mapping.get(str(status), "bg-secondary")
