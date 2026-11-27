"""audit.record(...): the one way to write an audit entry.

    from apps.audit import service as audit
    audit.record(audit.A.USER_ROLE, actor=request.user, target=user, before={...}, after={...}, sensitive=True)

sensitive=True  -> fail closed: a failed audit write raises, so the surrounding transaction (and the action) fails.
sensitive=False -> best effort: a failed write is logged and swallowed, inside a savepoint so the caller's own
                   transaction is not poisoned.
"""

import logging
import re

from django.db import transaction

from apps.core.utils import client_ip

from .context import current_request
from .models import AuditEntry

logger = logging.getLogger(__name__)

A = AuditEntry.Action
R = AuditEntry.Result

# Any key containing one of these words is never stored.
SECRET_KEY_RE = re.compile(r"pass|secret|token|key|hash|authorization|otp|cookie|session|credential", re.I)
MAX_TEXT = 500


def scrub(value):
    """Copy of value with secret-looking keys redacted and long text cut. Safe to store."""
    if isinstance(value, dict):
        return {str(k): ("[redacted]" if SECRET_KEY_RE.search(str(k)) else scrub(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:MAX_TEXT]


def _actor_fields(actor):
    """Actor id, label and role at this moment. The shared admin key is not a database user: id stays empty."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return {"actor_id": None, "actor_label": "", "actor_role": ""}
    pk = getattr(actor, "pk", None)
    label = getattr(actor, "email", "") or ""
    role = getattr(actor, "role", "") or ""
    if pk is None:  # TokenOwner (shared ADMIN_TOKEN)
        label = label or "shared-admin-token"
    return {"actor_id": pk, "actor_label": label[:254], "actor_role": role[:20]}


def _request_fields():
    request = current_request()
    if request is None:
        return {}
    ip = client_ip(request)
    return {
        "ip": ip if ip and ip != "unknown" else None,
        "user_agent": request.META.get("HTTP_USER_AGENT", "")[:300],
        "request_id": getattr(request, "audit_request_id", ""),
    }


def record(
    action,
    *,
    actor=None,
    target=None,
    target_type="",
    target_id="",
    before=None,
    after=None,
    reason="",
    result=R.SUCCESS,
    sensitive=False,
):
    """Write one entry. `target` may be a model instance (type and id are taken from it)."""
    if target is not None:
        target_type = target_type or target._meta.model_name
        target_id = target_id or str(getattr(target, "pk", "") or "")
    if actor is None:
        request = current_request()
        session_user = getattr(request, "user", None) if request is not None else None
        actor = session_user if getattr(session_user, "is_authenticated", False) else None
    try:
        with transaction.atomic():  # savepoint: a failure here must not break the caller's transaction
            return AuditEntry.objects.create(
                action=action,
                target_type=str(target_type)[:40],
                target_id=str(target_id)[:64],
                before=scrub(before) if before is not None else None,
                after=scrub(after) if after is not None else None,
                reason=str(reason or ""),
                result=result,
                **_actor_fields(actor),
                **_request_fields(),
            )
    except Exception:
        if sensitive:
            raise
        logger.exception("Audit write failed for %s", action)
        return None


def record_denied(request, view=None, status_code=403):
    """A refused call on a team route. Anonymous probes without any credentials are not logged (noise)."""
    user = getattr(request, "user", None)
    authenticated = bool(getattr(user, "is_authenticated", False))
    if not authenticated and not request.META.get("HTTP_AUTHORIZATION"):
        return None
    return record(
        A.DENIED,
        actor=user if authenticated else None,
        target_type="route",
        target_id=request.path[:64],
        after={"method": request.method, "status": status_code, "view": view.__class__.__name__ if view else ""},
        result=R.DENIED,
    )


def record_settings_change(name, before, after, *, actor=None, reason=""):
    """Hook for settings changes. No setting is editable in the app yet; the settings module (FL-21) calls this."""
    return record(
        A.SETTINGS,
        actor=actor,
        target_type="setting",
        target_id=name,
        before=before,
        after=after,
        reason=reason,
        sensitive=True,
    )
