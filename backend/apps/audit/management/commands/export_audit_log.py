"""Write one day of the audit log as JSON lines plus a SHA-256 file, on the app server.

    python manage.py export_audit_log                 # yesterday (UTC)
    python manage.py export_audit_log --date 2026-11-26 --out-dir /var/backups/flowly-audit

Files: audit-YYYY-MM-DD.jsonl and audit-YYYY-MM-DD.jsonl.sha256 (same layout as `sha256sum`).
Safe to run again for the same day: it rewrites both files from the table. The table is append-only, so a
changed hash on a past day means the file or the database was altered.
shortcut: the copy stays on the same server until the owner approves an off-box store (it costs money).
"""

import hashlib
import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit import service as audit
from apps.audit.models import AuditEntry


def write_private(path, data):
    """Write a file that only its owner can read (0600), whatever the umask. Replaces an older file of the day."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def entry_to_dict(e):
    return {
        "id": e.pk,
        "time": e.time.astimezone(timezone.utc).isoformat(),
        "actor_id": e.actor_id,
        "actor": e.actor_label,
        "actor_role": e.actor_role,
        "action": e.action,
        "target_type": e.target_type,
        "target_id": e.target_id,
        "before": e.before,
        "after": e.after,
        "reason": e.reason,
        "result": e.result,
        "ip": e.ip,
        "user_agent": e.user_agent,
        "request_id": e.request_id,
    }


class Command(BaseCommand):
    help = "Export one UTC day of the audit log to a JSONL file with a SHA-256 file next to it."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="UTC day, YYYY-MM-DD (default: yesterday)")
        parser.add_argument("--out-dir", help="Folder for the files (default: AUDIT_EXPORT_DIR)")

    def handle(self, *args, **options):
        try:
            day = (
                datetime.strptime(options["date"], "%Y-%m-%d").date()
                if options["date"]
                else (datetime.now(timezone.utc) - timedelta(days=1)).date()
            )
        except ValueError:
            raise CommandError("--date must look like 2026-11-26")
        out_dir = Path(options["out_dir"] or settings.AUDIT_EXPORT_DIR)
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        entries = AuditEntry.objects.filter(time__gte=start, time__lt=start + timedelta(days=1)).order_by("time", "id")

        # Fail closed: the export is itself an audited sensitive action, written in the same transaction.
        with transaction.atomic():
            audit.record(
                audit.A.EXPORT_AUDIT,
                target_type="audit_day",
                target_id=day.isoformat(),
                reason="Daily export (management command)",
                sensitive=True,
            )
            out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(out_dir, 0o700)  # the log holds emails and IP addresses: owner only
            name = f"audit-{day.isoformat()}.jsonl"
            body = "".join(json.dumps(entry_to_dict(e), ensure_ascii=False, sort_keys=True) + "\n" for e in entries)
            data = body.encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            write_private(out_dir / name, data)
            write_private(out_dir / f"{name}.sha256", f"{digest}  {name}\n".encode("utf-8"))
        self.stdout.write(f"{name}: {len(data)} bytes, sha256 {digest}")
