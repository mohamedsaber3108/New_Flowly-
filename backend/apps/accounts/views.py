import logging

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views.generic import TemplateView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit import service as audit
from apps.core.exceptions import envelope
from apps.core.negotiation import IgnoreClientContentNegotiation
from apps.security import gate
from apps.security import service as mfa_service

from . import services, session_cookie
from .serializers import (
    AvatarSerializer,
    ChangePasswordSerializer,
    DeleteAccountSerializer,
    GoogleCallbackSerializer,
    LoginSerializer,
    LogoutSerializer,
    MfaAwareRefreshSerializer,
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
        if not isinstance(request.data, dict):  # e.g. a JSON list: a normal 400, not a 500
            return envelope("Send a JSON object with email and password.", {"code": "bad_body"}, 400)
        email = str(request.data.get("email", "")).strip().lower()
        ip = gate.ip_of(request)
        try:
            gate.ensure_not_locked(email, ip)
        except gate.Refused as refused:
            return envelope(refused.message, {"code": refused.code}, refused.status)
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            codes = {c.code for errs in serializer.errors.values() for c in errs}
            if "disabled" in codes:  # wrong passwords are already logged by the user_login_failed signal
                audit.record(
                    audit.A.LOGIN_FAILED,
                    target_type="login",
                    after={"email": audit.safe_email(request.data.get("email", "")), "why": "account disabled"},
                    result=audit.R.DENIED,
                )
            if "authentication" in codes or "disabled" in codes:
                gate.password_failed(email, ip)
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
        try:  # entrance 2 (/team and the account portal): the second factor comes in the same request
            second_factor_proven = gate.second_factor(email, ip, user, request.data.get("code", ""))
        except gate.Refused as refused:
            return envelope(refused.message, {"code": refused.code}, refused.status)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        audit.record(audit.A.LOGIN, actor=user, target=user, after={"via": "api"})
        tokens = services.issue_tokens(
            user, mfa=second_factor_proven, team_session=session_cookie.is_staff_session(user)
        )
        user_data = UserSerializer(user, context={"request": request}).data
        if session_cookie.is_staff_session(user):  # FL-22: staff get cookies, and the body carries no token
            response = Response(
                {
                    "message": "Signed in.",
                    "data": {
                        "session": "cookie",
                        "session_seconds": settings.STAFF_SESSION_IDLE_SECONDS,
                        "user": user_data,
                    },
                }
            )
            return session_cookie.set_staff_session(response, request, tokens)
        return Response({"message": "Signed in.", "data": {**tokens, "user": user_data}})


class LogoutView(GenericAPIView):
    """Blacklists the refresh token and clears the staff cookies. A browser session (cookies) needs only the CSRF
    header, so it still works after the 15-minute access cookie has expired; a token client sends the refresh token."""

    serializer_class = LogoutSerializer
    authentication_classes: list = []  # checked below: the cookie case must not fail on an expired access cookie
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        return "Bearer"  # so a request with no sign-in is a 401, not a 403

    @extend_schema(tags=AUTH, summary="Invalidate a refresh token", responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        cookie_refresh = request.COOKIES.get(session_cookie.REFRESH_COOKIE)
        if cookie_refresh and not (isinstance(request.data, dict) and request.data.get("refresh")):
            session_cookie.enforce_csrf(request)
            try:
                RefreshToken(cookie_refresh).blacklist()
            except TokenError:
                pass  # already expired or blacklisted: the cookies are cleared either way
            return session_cookie.clear_staff_session(Response({"message": "Signed out.", "data": None}))
        if session_cookie.CookieJWTAuthentication().authenticate(request) is None:
            raise NotAuthenticated()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            return envelope("Invalid or expired refresh token.", None, 400)
        return session_cookie.clear_staff_session(Response({"message": "Signed out.", "data": None}))


class RefreshView(TokenRefreshView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    serializer_class = MfaAwareRefreshSerializer

    def get_authenticate_header(self, request):
        return "Bearer"  # an ended team session (session_expired, session_idle) is a 401, not a 403

    @extend_schema(tags=AUTH, summary="Exchange a refresh token for a new access token")
    def post(self, request, *args, **kwargs):
        cookie_refresh = request.COOKIES.get(session_cookie.REFRESH_COOKIE)
        if cookie_refresh and not (isinstance(request.data, dict) and request.data.get("refresh")):
            # A staff browser session: the same rules as the token refresh (including the "mfa" claim check), then
            # the rotated pair goes back into cookies and the body carries no token.
            session_cookie.enforce_csrf(request)
            serializer = self.get_serializer(data={"refresh": cookie_refresh})
            try:
                serializer.is_valid(raise_exception=True)
            except TokenError as exc:
                raise InvalidToken(exc.args[0])
            tokens = {
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data.get("refresh", cookie_refresh),
            }
            response = Response(
                {
                    "message": "Session refreshed.",
                    "data": {"session": "cookie", "session_seconds": settings.STAFF_SESSION_IDLE_SECONDS},
                }
            )
            return session_cookie.set_staff_session(response, request, tokens)
        # A refresh token sent in the body: customers only (FL-22). A team account's token would come back as new
        # tokens in JSON, which is what the cookie sign-in avoids, so it is refused unless ALLOW_STAFF_BEARER is on.
        raw = request.data.get("refresh") if isinstance(request.data, dict) else None
        if raw and not settings.ALLOW_STAFF_BEARER:
            from django.contrib.auth import get_user_model

            try:  # only reads the token: nothing is consumed or rotated here
                owner = get_user_model().objects.filter(pk=RefreshToken(raw).get("user_id")).first()
            except TokenError:
                owner = None  # an invalid token gets the normal 401 below
            if owner is not None and session_cookie.is_staff_session(owner):
                raise AuthenticationFailed(
                    "Team accounts sign in with the browser session, not a token.", "staff_bearer_refused"
                )
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
        # Entrance 4: Google sign-in has no place for a code, so owner/staff who need a second factor (or are locked
        # out) must use email + password + code instead. Customers are not affected.
        try:
            gate.ensure_not_locked(user.email, gate.ip_of(request))
            if mfa_service.second_factor_needed(user) or mfa_service.enrollment_required(user):
                raise gate.Refused(
                    "mfa_use_password", "Team accounts sign in with email, password and a verification code."
                )
        except gate.Refused as refused:
            if browser:
                return HttpResponseRedirect(f"{settings.SITE_URL}/account/?error=staff_mfa")
            return envelope(refused.message, {"code": refused.code}, refused.status)
        tokens = services.issue_tokens(user, team_session=session_cookie.is_staff_session(user))
        if session_cookie.is_staff_session(user):  # FL-22: no token in the address or the body for staff
            if browser:
                response = HttpResponseRedirect(f"{settings.SITE_URL}/account/#session=cookie")
            else:
                response = Response(
                    {
                        "message": "Signed in with Google.",
                        "data": {"session": "cookie", "user": UserSerializer(user, context={"request": request}).data},
                    }
                )
            return session_cookie.set_staff_session(response, request, tokens)
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
        from django.db import transaction
        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

        with transaction.atomic():  # all or nothing: no audit entry, no deletion
            for token in OutstandingToken.objects.filter(user=request.user):
                BlacklistedToken.objects.get_or_create(token=token)
            request.user.soft_delete(reason="Self-service account deletion")
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
