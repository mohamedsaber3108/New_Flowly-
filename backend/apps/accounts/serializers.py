from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class MfaAwareRefreshSerializer(TokenRefreshSerializer):
    """While REQUIRE_STAFF_MFA is on, owner/staff cannot refresh a token that was issued without a second factor
    (for example one issued before the switch). Rotation keeps the "mfa" claim, so a proven session stays proven."""

    def validate(self, attrs):
        from apps.security import service as mfa_service

        from . import session_cookie, session_limits

        token = RefreshToken(attrs["refresh"])  # an invalid or blacklisted token raises TokenError as usual
        user = User.objects.filter(pk=token.get("user_id")).first()
        if user is not None and session_cookie.is_staff_session(user):
            # FL-22b: the idle (30 minutes) and absolute (8 hours) limits; a team token with no session claims
            # (issued before they existed) is refused too. Customers are never checked.
            session_limits.check(token.payload, touch=True)
        if settings.REQUIRE_STAFF_MFA:
            if user is not None and mfa_service.is_team_user(user) and not token.get("mfa"):
                raise TokenError("Sign in again with your verification code.")
        return super().validate(attrs)


def _validate_password(value, user=None):
    try:
        validate_password(value, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return value


class UserSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "uuid",
            "email",
            "first_name",
            "last_name",
            "avatar",
            "role",
            "status",
            "email_verified",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.avatar.url) if request else obj.avatar.url

    @extend_schema_field(serializers.BooleanField())
    def get_email_verified(self, obj):
        from allauth.account.models import EmailAddress

        return EmailAddress.objects.filter(user=obj, email__iexact=obj.email, verified=True).exists()


class ProfileUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def validate_email(self, value):
        value = value.lower()
        qs = User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This email address is already in use.")
        return value


class AvatarSerializer(serializers.Serializer):
    avatar = serializers.ImageField()

    def validate_avatar(self, value):
        limit = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > limit:
            raise serializers.ValidationError(f"Image must be {settings.MAX_UPLOAD_SIZE_MB} MB or smaller.")
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in ("image/jpeg", "image/png", "image/webp", "image/gif"):
            raise serializers.ValidationError("Use a JPEG, PNG, WebP or GIF image.")
        return value


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, required=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        confirm = attrs.pop("password_confirm", None)
        if confirm is not None and confirm != attrs["password"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        _validate_password(
            attrs["password"],
            User(email=attrs["email"], first_name=attrs.get("first_name", ""), last_name=attrs.get("last_name", "")),
        )
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            role=User.Role.CUSTOMER,
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"), username=attrs["email"].lower(), password=attrs["password"]
        )
        if user is None or user.is_deleted:
            raise serializers.ValidationError("Invalid email or password.", code="authentication")
        if not user.is_active or user.status != User.Status.ACTIVE:
            raise serializers.ValidationError("This account is disabled.", code="disabled")
        attrs["user"] = user
        return attrs


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": "Choose a password you have not used just now."})
        _validate_password(attrs["new_password"], user)
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class GoogleCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=False)
    id_token = serializers.CharField(required=False)
    state = serializers.CharField(required=False, allow_blank=True)
    redirect_uri = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("code") and not attrs.get("id_token"):
            raise serializers.ValidationError("Provide an authorization code or Google id_token.")
        return attrs
