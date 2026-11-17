import uuid

import factory
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from apps.leads.models import Appointment, Request, RequestEvent

User = get_user_model()
PASSWORD = "Str0ng-Passw0rd!x"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.test")
    first_name = "Test"
    last_name = "User"
    role = "customer"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", PASSWORD)
        return model_class.objects.create_user(password=password, **kwargs)

    @factory.post_generation
    def verified(self, create, extracted, **kwargs):
        if create and extracted is not False:
            EmailAddress.objects.update_or_create(
                user=self, email=self.email, defaults={"primary": True, "verified": True}
            )


class StaffFactory(UserFactory):
    role = "staff"
    is_staff = True


class OwnerFactory(UserFactory):
    role = "owner"
    is_staff = True


class RequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Request

    id = factory.LazyFunction(uuid.uuid4)
    reference = factory.Sequence(lambda n: f"FLW-20261104-{n:08X}")
    kind = "discovery"
    audience = "business"
    name = "Visitor Name"
    email = factory.Sequence(lambda n: f"visitor{n}@example.test")
    organization = "Acme Co"
    language = "en"
    consent = True
    details = factory.LazyFunction(lambda: {"requirements": "Connect inventory with reporting automation."})


class AppointmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Appointment

    request = factory.SubFactory(RequestFactory)
    slot = "2026-12-01T11:00"
    date = "2026-12-01"
    time = "11:00"
    status = "provisional"


class RequestEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RequestEvent

    request = factory.SubFactory(RequestFactory)
    event_type = "submitted"
    status = "pending_review"
