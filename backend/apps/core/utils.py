import hmac
import json
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


mail_logger = logging.getLogger("flowly.mail")
_ADDRESS_RE = re.compile(r"[^@\s<>\"',;:()\[\]]+@[^@\s<>\"',;:()\[\]]+\.[^@\s<>\"',;:()\[\]]+")


def mask_address(value):
    """`a***@example.com`: enough to tell which mailbox, not enough to be personal data in a log."""
    text = str(value or "").strip()
    if not _ADDRESS_RE.fullmatch(text):
        return "[not an email]"
    local, domain = text.rsplit("@", 1)
    return f"{local[:1]}***@{domain}"


def mask_addresses_in(text):
    """Replace every email address inside free text (an SMTP error message can repeat the recipient)."""
    return _ADDRESS_RE.sub(lambda m: mask_address(m.group(0)), str(text))


def mail_mode():
    """ "configured" when mail is really sent by a server, "console" when it only goes to the log or to memory."""
    backend = settings.EMAIL_BACKEND
    not_real = ("console", "locmem", "dummy", "filebased")
    return "console" if any(word in backend for word in not_real) else "configured"


def send_template_email(subject, to, template, context=None):
    """Best-effort HTML email; failures are logged and never break the request.

    A failure writes ONE warning line to the logger "flowly.mail" (JSON): the template, how many recipients, their
    masked addresses and the error class. No full address, no message text.
    """
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
    except Exception as exc:  # noqa: BLE001 - email must never break a user flow
        mail_logger.warning(
            "mail_failed %s",
            json.dumps(
                {
                    "template": template,
                    "recipients": [mask_address(r) for r in recipients],
                    "error": type(exc).__name__,
                    "mode": mail_mode(),
                },
                sort_keys=True,
            ),
        )
        return False


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    proxies = getattr(settings, "REST_FRAMEWORK", {}).get("NUM_PROXIES", 0) or 0
    if forwarded and proxies:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if len(parts) >= proxies:
            return parts[-proxies]
    return request.META.get("REMOTE_ADDR", "unknown")
