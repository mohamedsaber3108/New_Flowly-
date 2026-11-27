"""Blacklist the outstanding refresh tokens of team accounts (owner, staff, viewer, anyone with admin rights).

Run once right after the FL-22 deploy: team tokens issued before it (7-day refresh tokens kept by the old /team page or
the portal) would otherwise keep working until they expire. Staff then sign in again and get cookies.

Safe to run again: a token already blacklisted is skipped, so a second run reports 0. `--before` limits the run to
tokens created before a moment (default: now), so a later run does not end sessions that started after the deploy.
Only counts are printed and logged, never a token or an address.
"""

import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.accounts.session_cookie import STAFF_ROLES

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Blacklist outstanding refresh tokens of team accounts (run once after the cookie sign-in deploy)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--before",
            help="Only tokens created before this ISO time, for example 2026-12-01T09:00:00+02:00 (default: now).",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now()
        if options["before"]:
            try:
                cutoff = datetime.fromisoformat(options["before"])
            except ValueError:
                raise CommandError("--before must be an ISO date and time, for example 2026-12-01T09:00:00+02:00.")
            if timezone.is_naive(cutoff):
                cutoff = timezone.make_aware(cutoff)
        team = get_user_model().objects.filter(Q(is_superuser=True) | Q(is_staff=True) | Q(role__in=STAFF_ROLES))
        pending = OutstandingToken.objects.filter(user__in=team, created_at__lt=cutoff).filter(
            blacklistedtoken__isnull=True
        )
        revoked = len(BlacklistedToken.objects.bulk_create([BlacklistedToken(token=t) for t in pending]))
        message = f"revoke_staff_tokens: team accounts {team.count()}, refresh tokens revoked {revoked}"
        logger.info(message)
        self.stdout.write(message)
