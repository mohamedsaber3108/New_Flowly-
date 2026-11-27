import io

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from tests.factories import PASSWORD, UserFactory

pytestmark = pytest.mark.django_db
ME = "/api/v1/users/me/"


def image_file(name="a.png", fmt="PNG", content_type="image/png", size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "purple").save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=content_type)


def test_get_me(auth_client, user):
    r = auth_client.get(ME)
    body = r.json()
    assert r.status_code == 200 and body["success"] is True
    assert body["data"]["email"] == user.email and "password" not in body["data"]
    assert body["data"]["email_verified"] is True


def test_patch_me_updates_names(auth_client, user):
    r = auth_client.patch(ME, {"first_name": "Nour", "last_name": "Ali"}, format="json")
    assert r.status_code == 200
    user.refresh_from_db()
    assert (user.first_name, user.last_name) == ("Nour", "Ali")


def test_patch_me_cannot_escalate_role(auth_client, user):
    auth_client.patch(ME, {"role": "owner", "is_staff": True, "is_superuser": True}, format="json")
    user.refresh_from_db()
    assert user.role == "customer" and not user.is_staff and not user.is_superuser


def test_patch_me_email_change_requires_reverification(auth_client, user):
    r = auth_client.patch(ME, {"email": "Fresh@Example.test"}, format="json")
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.email == "fresh@example.test"
    assert r.json()["data"]["email_verified"] is False and len(mail.outbox) == 1


def test_patch_me_duplicate_email_rejected(auth_client):
    UserFactory(email="taken@example.test")
    r = auth_client.patch(ME, {"email": "taken@example.test"}, format="json")
    assert r.status_code == 400 and r.json()["success"] is False


def test_avatar_upload_and_replace(auth_client, user):
    r = auth_client.post(f"{ME}avatar/", {"avatar": image_file()}, format="multipart")
    assert r.status_code == 200 and r.json()["data"]["avatar"].startswith("http")
    user.refresh_from_db()
    assert user.avatar.name.startswith("avatars/")
    first = user.avatar.name
    r = auth_client.post(f"{ME}avatar/", {"avatar": image_file("b.jpg", "JPEG", "image/jpeg")}, format="multipart")
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.avatar.name != first


@pytest.mark.parametrize("fmt, name, ctype", [("PNG", "a.png", "image/png"), ("JPEG", "a.jpg", "image/jpeg")])
def test_pillow_really_opens_and_resizes_the_uploaded_avatar(auth_client, user, fmt, name, ctype):
    """Runs Pillow itself (open, resize, re-save) on the stored file, so a broken Pillow major bump fails here."""
    r = auth_client.post(f"{ME}avatar/", {"avatar": image_file(name, fmt, ctype, size=(32, 16))}, format="multipart")
    assert r.status_code == 200
    user.refresh_from_db()
    with user.avatar.open("rb") as stored:
        with Image.open(stored) as img:
            assert img.format == fmt and img.size == (32, 16)
            small = img.convert("RGB").resize((8, 4))
    assert small.size == (8, 4)
    out = io.BytesIO()
    small.save(out, "PNG")
    assert Image.open(io.BytesIO(out.getvalue())).size == (8, 4)


def test_avatar_rejects_non_image_and_oversize(auth_client, settings):
    bad = SimpleUploadedFile("evil.png", b"not really an image", content_type="image/png")
    assert auth_client.post(f"{ME}avatar/", {"avatar": bad}, format="multipart").status_code == 400
    settings.MAX_UPLOAD_SIZE_MB = 0
    assert auth_client.post(f"{ME}avatar/", {"avatar": image_file()}, format="multipart").status_code == 400
    assert auth_client.post(f"{ME}avatar/", {}, format="multipart").status_code == 400


def test_avatar_requires_auth(api):
    assert api.post(f"{ME}avatar/", {"avatar": image_file()}, format="multipart").status_code == 401


def test_change_password(auth_client, user, password):
    r = auth_client.post(
        f"{ME}change-password/", {"current_password": "wrong", "new_password": "An0ther-Str0ng!pw"}, format="json"
    )
    assert r.status_code == 400
    r = auth_client.post(f"{ME}change-password/", {"current_password": password, "new_password": "123"}, format="json")
    assert r.status_code == 400
    r = auth_client.post(
        f"{ME}change-password/", {"current_password": password, "new_password": "An0ther-Str0ng!pw"}, format="json"
    )
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.check_password("An0ther-Str0ng!pw")


def test_delete_account_is_soft_and_revokes_tokens(api, user):
    refresh = RefreshToken.for_user(user)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    wrong = api.delete(ME, {"password": "wrong"}, format="json")
    assert wrong.status_code == 400
    r = api.delete(ME, {"password": PASSWORD}, format="json")
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.is_deleted and not user.is_active and user.deleted_at
    assert User.objects.filter(pk=user.pk).exists()
    api.credentials()
    assert api.post("/api/v1/auth/token/refresh/", {"refresh": str(refresh)}, format="json").status_code == 401
