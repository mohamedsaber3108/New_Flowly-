"""Break glass: remove the two-step verification of one owner/staff account, so the person can enrol again.

    python manage.py reset_staff_mfa --email owner@example.com

For the day the LAST owner loses the phone and the recovery codes (nobody is left to use the admin action).
Run it on the server only, as the app user. It writes a warning line to the "flowly.security" log and prints
what it did.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.security import service


class Command(BaseCommand):
    help = "Remove the authenticator device and recovery codes of one account (break-glass, run on the server)."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Email address of the account to reset.")

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No account with the email {email}.")
        if not service.is_team_user(user):
            raise CommandError(f"{email} is not an owner or staff account: there is nothing to reset.")
        had_device = service.MfaDevice.objects.filter(user=user).exists()
        service.reset_device(user, by="management command reset_staff_mfa")
        self.stdout.write(
            f"Two-step verification reset for {email}"
            + ("." if had_device else " (there was no device; recovery codes cleared).")
            + " They can enrol again at /account/mfa/enroll/."
        )
