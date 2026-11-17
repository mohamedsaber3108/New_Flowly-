import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.leads.models import Request
from tests.factories import RequestFactory, UserFactory

pytestmark = pytest.mark.django_db


def test_purge_e2e_dry_run_then_delete_only_test_data():
    RequestFactory(email="e2e-abc@example.test")
    keep = RequestFactory(email="real.customer@example.com")
    UserFactory(email="e2e-user@example.test")
    real_user = UserFactory(email="real.user@example.com")

    call_command("purge_e2e")  # dry run
    assert Request.objects.count() == 2 and User.objects.count() == 2

    call_command("purge_e2e", "--yes")
    assert list(Request.objects.values_list("pk", flat=True)) == [keep.pk]
    assert list(User.objects.values_list("pk", flat=True)) == [real_user.pk]
