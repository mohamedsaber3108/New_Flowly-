"""One structured log line (logger "flowly.admin") for a change made in the admin. Never a secret.

Until the audit log (PR #6) is merged, settings changes are recorded here. A follow-up (FL-21b) moves them into the
audit log. A line is JSON: event, who (user id and email of a signed-in staff member), and what changed
({"field": [old, new]}). The settings have no secret fields, so nothing here needs masking.
"""

import json
import logging

logger = logging.getLogger("flowly.admin")


def log_admin_event(event, user, **fields):
    payload = {"event": event, "user_id": getattr(user, "pk", None), "email": getattr(user, "email", ""), **fields}
    logger.info("admin_event %s", json.dumps(payload, sort_keys=True, default=str))
