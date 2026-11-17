"""Delete browser-test data created by e2e/run.mjs (addresses matching e2e-*@example.test only)."""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.leads.models import Request


class Command(BaseCommand):
    help = "Remove E2E test requests and users (email pattern e2e-*@example.test). Dry run unless --yes."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Actually delete.")

    def handle(self, *args, **options):
        requests = Request.objects.filter(email__istartswith="e2e-", email__iendswith="@example.test")
        users = User.objects.filter(email__istartswith="e2e-", email__iendswith="@example.test")
        self.stdout.write(f"{requests.count()} request(s), {users.count()} user(s) match.")
        if not options["yes"]:
            self.stdout.write("Dry run. Re-run with --yes to delete.")
            return
        # Appointments and events cascade with their request. These are synthetic test accounts, so they
        # are hard-deleted here; real users are only ever soft-deleted.
        requests.delete()
        users.delete()
        self.stdout.write(self.style.SUCCESS("Deleted."))
