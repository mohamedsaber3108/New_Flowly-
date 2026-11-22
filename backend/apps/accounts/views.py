import logging

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views.generic import TemplateView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core.exceptions import envelope
from apps.core.negotiation import IgnoreClientContentNegotiation

from . import services
from .serializers import (
    AvatarSerializer,
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    GoogleCallbackSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetSerializer,
    ProfileUpdateSerializer,
    RegisterSerializer,
    ResendVerificationSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)
AUTH = ["auth"]


class _Public(GenericAPIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]


class RegisterView(_Public):
    serializer_class = RegisterSerializer
    throttle_scope = "auth_register"

    @extend_schema(
        tags=AUTH, summary="Register with email and password", responses={201: UserSerializer, 400: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        services.send_verification_email(user, request)
        return Response(
            {
                "message": "Account created. Check your email to verify your address.",
                "data": UserSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(_Public):
    serializer_class = LoginSerializer
    throttle_scope = "auth_login"

    @extend_schema(
        tags=AUTH,
        summary="Login with email and password; returns a JWT pair",
        responses={200: OpenApiTypes.OBJECT, 401: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            codes = {c.code for errs in serializer.errors.values() for c in errs}
            if "authentication" in codes or "disabled" in codes:
                return envelope(
                    "Invalid email or password." if "authentication" in codes else "This account is disabled.",
                    None,
                    401 if "authentication" in codes else 403,
                )
            serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        if settings.REQUIRE_EMAIL_VERIFICATION and not services.is_email_verified(user):
            return envelope("Verify your email address before signing in.", {"code": "email_not_verified"}, 403)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        return Response(
            {
                "message": "Signed in.",
                "data": {
                    **services.issue_tokens(user),
                    "user": UserSerializer(user, context={"request": request}).data,
                },
            }
        )


class LogoutView(GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=AUTH, summary="Invalidate a refresh token", responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return envelope("Invalid or expired refresh token.", None, 400)
        return Response({"message": "Signed out.", "data": None})


class RefreshView(TokenRefreshView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(tags=AUTH, summary="Exchange a refresh token for a new access token")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class ResendVerificationView(_Public):
    serializer_class = ResendVerificationSerializer
    throttle_scope = "auth_reset"

    @extend_schema(tags=AUTH, summary="Resend the email verification link", responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from django.contrib.auth import get_user_model

        user = (
            get_user_model()
            .objects.filter(email__iexact=serializer.validated_data["email"], is_active=True, is_deleted=False)
            .first()
        )
        if user:
            services.send_verification_email(user, request)
        # Same answer either way: do not reveal which emails have accounts.
        return Response({"message": "If the account exists and is unverified, a new link was sent.", "data": None})


class VerifyEmailView(APIView):
    content_negotiation_class = IgnoreClientContentNegotiation
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_reset"

    @extend_schema(
        tags=AUTH,
        summary="Confirm an email address from the emailed key",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def get(self, request, key):
        address = services.confirm_email(key, request._request)
        wants_html = "text/html" in request.headers.get("Accept", "") and "application/json" not in request.headers.get(
            "Accept", ""
        )
        if address is None:
            if wants_html:
                return HttpResponseRedirect(f"{settings.SITE_URL}/account/?verified=0")
            return envelope("This verification link is invalid or has expired.", None, 400)
        if wants_html:
            return HttpResponseRedirect(f"{settings.SITE_URL}/account/?verified=1")
        return Response({"message": "Email verified.", "data": None})


class PasswordResetView(_Public):
    serializer_class = PasswordResetSerializer
    throttle_scope = "auth_reset"

    @extend_schema(tags=AUTH, summary="Request a password reset email", responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.send_password_reset(serializer.validated_data["email"])
        return Response({"message": "If an account exists for this email, a reset link was sent.", "data": None})


class PasswordResetConfirmView(_Public):
    serializer_class = PasswordResetConfirmSerializer
    throttle_scope = "auth_reset"

    @extend_schema(
        tags=AUTH,
        summary="Set a new password using the emailed uid and token",
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        from .serializers import _validate_password

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = services.resolve_reset_user(data["uid"], data["token"])
        if user is None:
            return envelope("This reset link is invalid or has expired.", None, 400)
        try:
            _validate_password(data["new_password"], user)
        except Exception as exc:  # DRF ValidationError
            return envelope("Validation failed.", {"new_password": getattr(exc, "detail", [str(exc)])}, 400)
        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        return Response({"message": "Password updated. You can now sign in.", "data": None})


class GoogleStartView(_Public):
    content_negotiation_class = IgnoreClientContentNegotiation
    throttle_scope = "auth_login"
    serializer_class = None

    @extend_schema(
        tags=AUTH,
        summary="Get the Google OAuth authorization URL",
        responses={200: OpenApiTypes.OBJECT},
        parameters=[OpenApiParameter("redirect", bool, description="302 redirect to Google instead of JSON")],
    )
    def get(self, request):
        try:
            url, state = services.google_authorization_url()
        except services.GoogleAuthError as exc:
            return envelope(str(exc), None, 503)
        if request.query_params.get("redirect") in ("1", "true"):
            return HttpResponseRedirect(url)
        return Response({"data": {"authorization_url": url, "state": state}, "message": ""})


class GoogleCallbackView(_Public):
    content_negotiation_class = IgnoreClientContentNegotiation
    throttle_scope = "auth_login"
    serializer_class = GoogleCallbackSerializer

    def _complete(self, request, code=None, id_token=None, state=None, redirect_uri=None, browser=False):
        try:
            if code and state is not None:
                services.verify_state(state)
            user = services.google_sign_in(code=code, id_token=id_token, redirect_uri=redirect_uri)
        except services.GoogleAuthError as exc:
            if browser:
                return HttpResponseRedirect(f"{settings.SITE_URL}/account/?error=google")
            return envelope(str(exc), None, 400)
        tokens = services.issue_tokens(user)
        if browser:
            fragment = f"access={tokens['access']}&refresh={tokens['refresh']}"
            return HttpResponseRedirect(f"{settings.SITE_URL}/account/#{fragment}")
        return Response(
            {
                "message": "Signed in with Google.",
                "data": {**tokens, "user": UserSerializer(user, context={"request": request}).data},
            }
        )

    @extend_schema(
        tags=AUTH,
        summary="Google redirects the browser here; finishes sign-in",
        parameters=[OpenApiParameter("code", str), OpenApiParameter("state", str)],
        responses={200: OpenApiTypes.OBJECT, 302: None},
    )
    def get(self, request):
        code = request.query_params.get("code")
        if not code:
            return HttpResponseRedirect(f"{settings.SITE_URL}/account/?error=google")
        wants_json = (
            "application/json" in request.headers.get("Accept", "") or request.query_params.get("format") == "json"
        )
        return self._complete(request, code=code, state=request.query_params.get("state", ""), browser=not wants_json)

    @extend_schema(
        tags=AUTH,
        summary="Sign in with a Google authorization code or id_token (SPA flow)",
        request=GoogleCallbackSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return self._complete(
            request,
            code=d.get("code"),
            id_token=d.get("id_token"),
            state=d.get("state") or None,
            redirect_uri=d.get("redirect_uri") or None,
        )


# --- Current user ---------------------------------------------------------


class MeView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    @extend_schema(tags=["users"], summary="Current user profile", responses={200: UserSerializer})
    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    @extend_schema(
        tags=["users"], summary="Update name or email", request=ProfileUpdateSerializer, responses={200: UserSerializer}
    )
    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        old_email = request.user.email
        user = serializer.save()
        message = "Profile updated."
        if user.email != old_email:
            from allauth.account.models import EmailAddress

            EmailAddress.objects.filter(user=user).delete()
            services.send_verification_email(user, request)
            message = "Profile updated. Verify your new email address."
        return Response({"message": message, "data": UserSerializer(user, context={"request": request}).data})

    @extend_schema(
        tags=["users"],
        summary="Soft-delete the account",
        request=DeleteAccountSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data.get("password")
        if request.user.has_usable_password() and not (password and request.user.check_password(password)):
            return envelope(
                "Enter your current password to delete the account.", {"password": ["Incorrect password."]}, 400
            )
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        for token in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=token)
        request.user.soft_delete()
        return Response({"message": "Account deleted.", "data": None})


class AvatarView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AvatarSerializer
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["users"],
        summary="Upload an avatar image (multipart field 'avatar')",
        request=AvatarSerializer,
        responses={200: UserSerializer},
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if user.avatar:
            user.avatar.delete(save=False)
        user.avatar = serializer.validated_data["avatar"]
        user.save(update_fields=["avatar", "updated_at"])
        return Response({"message": "Avatar updated.", "data": UserSerializer(user, context={"request": request}).data})


class ChangePasswordView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    @extend_schema(
        tags=["users"], summary="Change password (current password required)", responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"message": "Password changed.", "data": None})


class PortalView(TemplateView):
    """Account portal page (login, register, dashboard, profile). Talks to /api/v1 from the browser."""

    template_name = "account/portal.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["google_enabled"] = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
        return context
