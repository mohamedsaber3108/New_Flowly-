"""Enrolment of the authenticator app. Two doors, same service:

* the web page /account/mfa/enroll/ (Django session, for people at a browser), and
* two API calls /api/v1/auth/mfa/enroll/ and /confirm/ (email + password in the body).

Both ask for the email and password (a person who is refused at sign-in because they have no second factor yet
cannot hold a token), count wrong passwords towards the sign-in lockout, and refuse to replace a confirmed device.
"""

import time

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import render
from django.views import View
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import envelope

from . import gate, service

User = get_user_model()
SESSION_KEY = "mfa_enroll_user_id"
SESSION_TIME = "mfa_enroll_started"
SESSION_SECONDS = 600  # the page step must be finished within 10 minutes


def _team_user_for_password(request, email, password):
    """The user if the password is right and the account may enrol. Raises gate.Refused otherwise."""
    email = (email or "").strip().lower()
    gate.ensure_not_locked(email)
    user = authenticate(request, username=email, password=password or "")
    if user is None or getattr(user, "is_deleted", False) or not user.is_active:
        gate.password_failed(email)
        raise gate.Refused("invalid_credentials", "Invalid email or password.", 401)
    if not service.is_team_user(user):
        raise gate.Refused("not_team", "Two-step verification is only for owner and staff accounts.", 403)
    return user


def _not_configured():
    return gate.Refused("mfa_not_configured", "Two-step verification is not configured on this server yet.", 503)


# --- API ---------------------------------------------------------------------------------------------------------


class EnrollApiView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    def post(self, request):
        try:
            user = _team_user_for_password(request, request.data.get("email"), request.data.get("password"))
            try:
                secret, uri = service.start_enrollment(user)
            except service.AlreadyEnrolled:
                return envelope("Two-step verification is already set up. Ask the owner to reset it.", None, 409)
            except ImproperlyConfigured:
                raise _not_configured()
        except gate.Refused as refused:
            return envelope(refused.message, {"code": refused.code}, refused.status)
        return Response(
            {
                "message": "Add this key to your authenticator app, then confirm with a code.",
                "data": {"secret": secret, "otpauth_uri": uri},
            }
        )


class ConfirmApiView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_scope = "auth_login"

    def post(self, request):
        try:
            user = _team_user_for_password(request, request.data.get("email"), request.data.get("password"))
            try:
                codes = service.confirm_enrollment(user, request.data.get("code"))
            except service.NotEnrolling:
                return envelope("Start the setup first.", None, 409)
            except ImproperlyConfigured:
                raise _not_configured()
            if codes is None:
                gate.password_failed(user.email)  # a wrong code counts like a wrong password
                return envelope("That verification code is not valid.", {"code": "mfa_invalid"}, 400)
        except gate.Refused as refused:
            return envelope(refused.message, {"code": refused.code}, refused.status)
        return Response(
            {
                "message": "Two-step verification is on. Save these recovery codes: each works once.",
                "data": {"recovery_codes": codes},
            }
        )


# --- Web page ----------------------------------------------------------------------------------------------------


class EnrollPageView(View):
    template_name = "mfa/enroll.html"

    def get(self, request):
        return render(request, self.template_name, {"step": "credentials"})

    def post(self, request):
        if request.POST.get("step") == "confirm":
            return self._confirm(request)
        return self._credentials(request)

    def _credentials(self, request):
        try:
            user = _team_user_for_password(request, request.POST.get("email"), request.POST.get("password"))
            try:
                secret, uri = service.start_enrollment(user)
            except service.AlreadyEnrolled:
                return self._page(
                    request, "credentials", error="Two-step verification is already set up. Ask the owner to reset it."
                )
            except ImproperlyConfigured:
                raise _not_configured()
        except gate.Refused as refused:
            return self._page(request, "credentials", error=refused.message, status=refused.status)
        request.session[SESSION_KEY] = user.pk
        request.session[SESSION_TIME] = int(time.time())
        return self._page(request, "confirm", secret=secret, uri=uri)

    def _confirm(self, request):
        user_id = request.session.get(SESSION_KEY)
        started = request.session.get(SESSION_TIME, 0)
        user = User.objects.filter(pk=user_id, is_active=True, is_deleted=False).first() if user_id else None
        if user is None or int(time.time()) - started > SESSION_SECONDS:
            return self._page(request, "credentials", error="The setup took too long. Start again.")
        try:
            gate.ensure_not_locked(user.email)
            codes = service.confirm_enrollment(user, request.POST.get("code"))
        except gate.Refused as refused:
            return self._page(request, "credentials", error=refused.message, status=refused.status)
        except (service.NotEnrolling, ImproperlyConfigured):
            return self._page(request, "credentials", error="Start the setup again.")
        if codes is None:
            gate.password_failed(user.email)
            return self._page(
                request,
                "confirm",
                error="That verification code is not valid. Try the next one.",
                status=400,
                resume=user,
            )
        request.session.pop(SESSION_KEY, None)
        request.session.pop(SESSION_TIME, None)
        return self._page(request, "done", codes=codes)

    def _page(self, request, step, error="", status=200, codes=None, secret="", uri="", resume=None):
        context = {"step": step, "error": error, "codes": codes, "secret": secret, "uri": uri}
        if resume is not None:  # a wrong code on the confirm step: show the same secret again
            device = resume.mfa_device
            context["secret"] = service.decrypt_secret(device.secret)
            context["uri"] = service.otpauth_uri(resume, context["secret"])
        response = render(request, self.template_name, context, status=status)
        response["Cache-Control"] = "no-store"  # the page shows a secret and recovery codes
        return response
