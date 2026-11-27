"""One structured log line (logger "flowly.admin") for a change made in the admin. Never a secret.

Settings and blocked-day changes are ALSO written to the audit log (FL-21b, `audit.record`); this line stays as an
operations log that can be read on the server without the admin. A line is JSON: event, who (user id and email of a
signed-in staff member), and what changed ({"field": [old, new]}). The settings have no secret fields, so nothing here
needs masking.
"""

import json
import logging

logger = logging.getLogger("flowly.admin")


def log_admin_event(event, user, **fields):
    payload = {"event": event, "user_id": getattr(user, "pk", None), "email": getattr(user, "email", ""), **fields}
    logger.info("admin_event %s", json.dumps(payload, sort_keys=True, default=str))
