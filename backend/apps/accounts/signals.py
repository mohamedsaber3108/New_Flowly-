import logging

from allauth.account.signals import email_confirmed
from django.dispatch import receiver

from apps.core.utils import send_template_email

logger = logging.getLogger(__name__)


@receiver(email_confirmed)
def on_email_confirmed(request, email_address, **kwargs):
    """Once an email is verified: attach earlier anonymous requests made with that
    email to the account (so they appear in the dashboard) and send a welcome email."""
    from apps.leads.models import Request

    user = email_address.user
    linked = Request.objects.filter(user__isnull=True, email__iexact=email_address.email).update(user=user)
    if linked:
        logger.info("Linked %s earlier request(s) to user %s", linked, user.pk)
    send_template_email(
        "Welcome to Flowly",
        email_address.email,
        "emails/welcome.html",
        {"name": user.first_name or user.email},
    )
