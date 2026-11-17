"""Create the first superuser, a staff user and (optionally) demo requests.

Usage:
  python manage.py seed_demo                 # superuser + staff from env vars
  python manage.py seed_demo --demo-data     # also create sample requests
Environment (all optional; sensible dev defaults are NOT used in production):
  DJANGO_SUPERUSER_EMAIL, DJANGO_SUPERUSER_PASSWORD
  DEMO_STAFF_EMAIL, DEMO_STAFF_PASSWORD
"""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from decouple import config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.leads import services
from apps.leads.models import Request

User = get_user_model()


def _verified_user(email, password, **extra):
    user = User.objects.filter(email__iexact=email).first()
    created = user is None
    if created:
        user = User.objects.create_user(email=email, password=password, **extra)
    EmailAddress.objects.update_or_create(user=user, email=user.email, defaults={"primary": True, "verified": True})
    return user, created


class Command(BaseCommand):
    help = "Create the initial superuser, a staff user and optional demo requests (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--demo-data", action="store_true", help="Also create sample requests.")

    def handle(self, *args, **options):
        email = config("DJANGO_SUPERUSER_EMAIL", default="admin@flowly.local")
        password = config("DJANGO_SUPERUSER_PASSWORD", default="")
        generated = False
        if not password:
            if not settings.DEBUG:
                self.stderr.write("Set DJANGO_SUPERUSER_PASSWORD to create the production superuser.")
                return
            password, generated = "FlowlyAdmin!2026", True
        superuser, created = _verified_user(
            email,
            password,
            first_name="Flowly",
            last_name="Owner",
            role=User.Role.OWNER,
            is_staff=True,
            is_superuser=True,
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Superuser created: {email}"))
            if generated:
                self.stdout.write("  (development password: FlowlyAdmin!2026 - change it)")
        else:
            self.stdout.write(f"Superuser exists: {email}")

        staff_email = config("DEMO_STAFF_EMAIL", default="staff@flowly.local" if settings.DEBUG else "")
        staff_password = config("DEMO_STAFF_PASSWORD", default="") or ("FlowlyStaff!2026" if settings.DEBUG else "")
        if staff_email and staff_password:
            _, made = _verified_user(
                staff_email, staff_password, first_name="Flowly", last_name="Staff", role=User.Role.STAFF, is_staff=True
            )
            self.stdout.write(f"Staff user {'created' if made else 'exists'}: {staff_email}")

        if options["demo_data"]:
            self._demo_requests()

    def _demo_requests(self):
        if Request.objects.filter(details__demo=True).exists():
            self.stdout.write("Demo requests already exist.")
            return
        day = datetime.now(ZoneInfo("Africa/Cairo")).date() + timedelta(days=3)
        while day.weekday() in (4, 5):
            day += timedelta(days=1)
        samples = [
            (
                "discovery",
                "business",
                "Mona Adel",
                "mona@example.test",
                "Nile Logistics",
                "We need to connect our inventory system with automated weekly reporting.",
            ),
            (
                "consultation",
                "government",
                "Karim Samir",
                "karim@example.test",
                "Ministry Digital Office",
                "Citizen service portal with internal workflow approvals and hosting constraints.",
            ),
            (
                "contact",
                "agency",
                "Layla Hassan",
                "layla@example.test",
                "Pixel Agency",
                "Exploring a white-label CRM and content platform for our own clients.",
            ),
        ]
        for index, (kind, audience, name, email, org, need) in enumerate(samples):
            payload = {
                "requestKey": uuid.uuid4(),
                "name": name,
                "email": email,
                "organization": org,
                "kind": kind,
                "audience": audience,
                "requirements": need,
                "consent": True,
                "timezone": "Africa/Cairo",
                "language": "en",
                "demo": True,
                "department": "Digital transformation" if audience == "government" else "",
                "date": day.isoformat() if kind == "consultation" else None,
                "time": "11:00" if kind == "consultation" else None,
            }
            services.create_request(payload)
        self.stdout.write(self.style.SUCCESS(f"Created {len(samples)} demo requests."))
