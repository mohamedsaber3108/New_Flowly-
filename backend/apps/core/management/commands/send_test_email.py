"""Send one test email, to check the mail settings after they are set on the server.

    python manage.py send_test_email --to someone@example.com

Prints the result and the mail mode ("configured" = a mail server sends it, "console" = it is only written to the
log). It uses the same settings as the site (EMAIL_HOST, EMAIL_HOST_USER, DEFAULT_FROM_EMAIL, ...) and prints none of
the secrets. Exits non-zero when the send fails, so it can be used in a script.
"""

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError

from apps.core.utils import mail_mode, mask_address, mask_addresses_in


class Command(BaseCommand):
    help = "Send one test email with the site's mail settings and report whether it worked."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Address that should receive the test email.")

    def handle(self, *args, **options):
        to = options["to"].strip()
        if mask_address(to) == "[not an email]":
            raise CommandError("--to must be an email address.")
        mode = mail_mode()
        self.stdout.write(f"Mail mode: {mode}. From: {settings.DEFAULT_FROM_EMAIL}. To: {mask_address(to)}.")
        if mode == "console":
            self.stdout.write(
                "Note: nothing is really sent in this mode (the message only goes to the log). "
                "Set EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD in backend/.env first."
            )
        message = EmailMultiAlternatives(
            "Flowly test email / رسالة اختبار من Flowly",
            "This is a test message from Flowly. If you can read it, sending works.\n"
            "هذه رسالة اختبار من Flowly. إذا وصلتك فالإرسال يعمل.",
            settings.DEFAULT_FROM_EMAIL,
            [to],
        )
        try:
            sent = message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - report every kind of failure the same way
            raise CommandError(f"FAILED: {type(exc).__name__}: {mask_addresses_in(exc)}") from exc
        if not sent:
            raise CommandError("FAILED: the mail backend reported 0 messages sent.")
        if mode == "console":
            # The console backend "succeeds" without sending anything: do not report that as OK.
            self.stdout.write(self.style.WARNING("console backend: not sent, check the log"))
            return
        self.stdout.write(self.style.SUCCESS("OK: the mail server accepted the message. Now check the inbox and spam."))
