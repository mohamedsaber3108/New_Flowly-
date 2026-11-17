import hmac
import logging
import re
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def iso(value):
    """UTC ISO-8601 with millisecond precision and a Z suffix (JS Date compatible)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def html_to_text(html):
    """Plain-text alternative that keeps line breaks (so links stay on their own line)."""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", html)
    text = strip_tags(text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def send_template_email(subject, to, template, context=None):
    """Best-effort HTML email; failures are logged and never break the request."""
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [r for r in recipients if r]
    if not recipients:
        return False
    ctx = {"frontend_url": settings.FRONTEND_URL, "site_url": settings.SITE_URL, **(context or {})}
    try:
        html = render_to_string(template, ctx)
        message = EmailMultiAlternatives(subject, html_to_text(html), settings.DEFAULT_FROM_EMAIL, recipients)
        message.attach_alternative(html, "text/html")
        message.send(fail_silently=False)
        return True
    except Exception:  # noqa: BLE001 - email must never break a user flow
        logger.exception("Email '%s' could not be sent", subject)
        return False


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    proxies = getattr(settings, "REST_FRAMEWORK", {}).get("NUM_PROXIES", 0) or 0
    if forwarded and proxies:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= proxies:
            return parts[-proxies]
    return request.META.get("REMOTE_ADDR", "unknown")
