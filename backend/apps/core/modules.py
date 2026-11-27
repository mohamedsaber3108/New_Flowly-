"""The module registry: which parts of the site exist, who uses them, whether their backend works, and whether they
are switched on. Read-only for now (shown on the admin settings page).

A check is a small function returning (ok, detail). It runs only a cheap local test (a database query, a setting), so
the page never waits on the outside world.
"""

from django.conf import settings
from django.db import connection


def mail_mode():
    """ "configured" when a mail server sends the mail, "console" when it only goes to the log or to memory.
    (The same rule as the mail PR's helper of the same name; keep them equal when both are merged.)"""
    backend = settings.EMAIL_BACKEND
    return "console" if any(word in backend for word in ("console", "locmem", "dummy", "filebased")) else "configured"


def _database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - any failure means the backend is not working
        return False, f"database error: {type(exc).__name__}"
    return True, "database answers"


def _always():
    return True, "no external service"


def _mail():
    mode = mail_mode()
    return True, "mail is sent by a mail server" if mode == "configured" else "console: messages go to the log only"


def registry(settings_snapshot):
    """Rows for the admin: id, name, roles, backend health, on/off."""
    s = settings_snapshot
    modules = [
        ("intake", "Request intake (public forms)", "visitors", _database, s.intake_enabled),
        ("booking", "Consultation booking", "visitors", _database, s.intake_enabled),
        ("assistant", "Service assistant (chat)", "visitors", _always, s.assistant_enabled),
        ("team-console", "Team console (/team)", "owner, staff, viewer", _database, True),
        ("account-portal", "Customer account portal", "customers", _database, True),
        ("admin", "Django admin", "owner, staff, viewer (read-only)", _database, True),
        ("mail", "Email alerts and receipts", "system", _mail, mail_mode() == "configured"),
    ]
    rows = []
    for module_id, name, roles, check, enabled in modules:
        ok, detail = check()
        rows.append(
            {"id": module_id, "name": name, "roles": roles, "healthy": ok, "detail": detail, "enabled": bool(enabled)}
        )
    return rows
