"""Structured security log lines (logger "flowly.security"). One JSON object per line, never a secret.

Used until the audit log (PR #6) is merged: a follow-up (FL-09b) moves these events into it.
Allowed fields are plain facts: event name, user id, email, IP address, who did it. Never a code, key or password.
"""

import json
import logging

logger = logging.getLogger("flowly.security")


def log_event(event, level=logging.INFO, **fields):
    payload = {"event": event, **{k: v for k, v in fields.items() if v not in (None, "")}}
    logger.log(level, "security_event %s", json.dumps(payload, sort_keys=True, default=str))
