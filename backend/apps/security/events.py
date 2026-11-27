"""Structured security log lines (logger "flowly.security"). One JSON object per line, never a secret.

Each of these events is ALSO written to the audit log (FL-09b: `audit.record` in service.py and lockout.py); the log
line stays as an operations log that can be read on the server.
Allowed fields are plain facts: event name, user id, email of a KNOWN account, IP address, who did it.
Text that a visitor typed into the email box is never logged as typed: it can be a password pasted by mistake.
Use mask_email() for it.
"""

import json
import logging
import re

logger = logging.getLogger("flowly.security")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def mask_email(value):
    """`a***@example.com` for something that looks like an email address, otherwise a fixed text.
    The log keeps enough to tell which address was attacked, not enough to be a password."""
    text = str(value or "").strip()
    if len(text) > 254 or not _EMAIL_RE.match(text):
        return "[not an email]"
    local, domain = text.rsplit("@", 1)
    return f"{local[:1]}***@{domain}"


def log_event(event, level=logging.INFO, **fields):
    payload = {"event": event, **{k: v for k, v in fields.items() if v not in (None, "")}}
    logger.log(level, "security_event %s", json.dumps(payload, sort_keys=True, default=str))
