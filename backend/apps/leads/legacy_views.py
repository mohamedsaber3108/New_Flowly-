"""Original frontend API contract (/api/*): raw JSON bodies and { error } failures.

The React app (components/Intake.tsx, RequestStatus.tsx, Assistant.tsx, TeamConsole.tsx)
calls these paths unchanged, so the existing frontend works without modification.
"""

import json
import logging

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import service as audit
from apps.core.exceptions import legacy_exception_handler
from apps.core.permissions import READ_ROLES, TEAM_ROLES, has_role

from . import assistant as assistant_service
from . import catalog, intake, services
from .auth import TEAM_AUTHENTICATION, actor_for, optional_user
from .models import Request
from .serializers import (
    REFERENCE_RE,
    AssistantSerializer,
    RequestCreateSerializer,
    RequestLookupSerializer,
    RequestUpdateSerializer,
    legacy_row,
)

logger = logging.getLogger(__name__)
MAX_BODY = 25000


def allowed_origins(request):
    origins = {request.build_absolute_uri("/").rstrip("/")}
    for extra in (settings.PUBLIC_ORIGIN, settings.FRONTEND_URL, *settings.CORS_ALLOWED_ORIGINS):
        if extra:
            origins.add(extra.rstrip("/"))
    return origins


def origin_ok(request):
    origin = request.META.get("HTTP_ORIGIN")
    return not origin or origin.rstrip("/") in allowed_origins(request)


class LegacyAPIView(APIView):
    renderer_classes = [JSONRenderer]
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []  # intake endpoints throttle manually, after the idempotency check

    def get_exception_handler(self):
        return legacy_exception_handler

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @staticmethod
    def error(status, message):
        return Response({"error": message}, status=status)

    def body(self, request):
        """Parse JSON from the raw body. Returns (data, error_response)."""
        raw = request.body
        if len(raw) > MAX_BODY:
            return None, self.error(413, "Request too large")
        try:
            data = json.loads(raw.decode("utf-8") or "null")
        except (ValueError, UnicodeDecodeError):
            return None, self.error(400, "Invalid request body")
        if not isinstance(data, dict):
            return None, self.error(400, "Invalid request body")
        return data, None

    def intake_error(self, exc: intake.IntakeError):
        return self.error(exc.status, exc.message)


class HealthView(LegacyAPIView):
    @extend_schema(
        tags=["frontend-api"],
        summary="App and storage readiness",
        responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except DatabaseError:
            return Response({"status": "degraded", "service": "flowly-web", "storage": "unavailable"}, status=503)
        # sharedAdminToken tells /team whether to show the shared-key field. A boolean only, never the key.
        return Response(
            {
                "status": "ok",
                "service": "flowly-web",
                "storage": "ok",
                "sharedAdminToken": bool(
                    settings.ALLOW_SHARED_ADMIN_TOKEN
                    and not settings.REQUIRE_STAFF_MFA
                    and len(settings.ADMIN_TOKEN or "") >= 32
                ),
            }
        )


class RequestsView(LegacyAPIView):
    @extend_schema(
        tags=["frontend-api"],
        summary="Submit a discovery, consultation or contact request",
        description="Used by /start, /contact and /consultation. Safe to retry with the same requestKey.",
        request=RequestCreateSerializer,
        responses={201: OpenApiTypes.OBJECT, 200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        if not origin_ok(request):
            return self.error(403, "Request origin not allowed")
        data, failure = self.body(request)
        if failure:
            return failure
        try:
            status, body = intake.submit_request(request, data, user=optional_user(request))
        except intake.IntakeError as exc:
            return self.intake_error(exc)
        except DatabaseError:
            logger.exception("Flowly request could not be saved")
            return self.error(503, "The request could not be saved. Please try again.")
        return Response(body, status=status)


class AvailabilityView(LegacyAPIView):
    @extend_schema(
        tags=["frontend-api"],
        summary="Busy consultation times for a date",
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        try:
            return Response(intake.availability(request.query_params.get("date", "")))
        except intake.IntakeError as exc:
            return self.intake_error(exc)
        except DatabaseError:
            return self.error(503, "Availability temporarily unavailable")


class RequestStatusView(LegacyAPIView):
    @extend_schema(
        tags=["frontend-api"],
        summary="Customer lookup by reference and email",
        request=RequestLookupSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        if not origin_ok(request):
            return self.error(403, "Request origin not allowed")
        data, failure = self.body(request)
        if failure:
            return failure
        try:
            return Response(intake.lookup_request(request, data))
        except intake.IntakeError as exc:
            return self.intake_error(exc)
        except DatabaseError:
            return self.error(503, "Status is temporarily unavailable.")


class AssistantView(LegacyAPIView):
    @extend_schema(tags=["frontend-api"], summary="Assistant mode (ai or guide)", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"mode": "ai" if assistant_service.configured() else "guide"})

    @extend_schema(
        tags=["frontend-api"],
        summary="Ask the service-discovery assistant",
        request=AssistantSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def post(self, request):
        if not origin_ok(request):
            return self.error(403, "Request origin not allowed")
        data, failure = self.body(request)
        if failure:
            return failure
        try:
            return Response(intake.assistant_reply(request, data, user=optional_user(request)))
        except intake.IntakeError as exc:
            return self.intake_error(exc)
        except Exception:  # noqa: BLE001
            logger.exception("Assistant failed")
            return self.error(503, "Unable to answer right now. Please try again.")


class TeamLegacyView(LegacyAPIView):
    authentication_classes = TEAM_AUTHENTICATION

    def team_gate(self, request, roles):
        if not request.user or not request.user.is_authenticated:
            return self.error(401, "Unauthorized")
        if not has_role(request.user, roles):
            audit.record_denied(request, self, 403)
            return self.error(403, "Forbidden")
        return None


class AdminRequestsView(TeamLegacyView):
    @extend_schema(tags=["frontend-api"], summary="Team: list the latest 500 requests", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        denied = self.team_gate(request, READ_ROLES)
        if denied:
            return denied
        try:
            rows = Request.objects.prefetch_related("appointments").order_by("-created_at")[:500]
            return Response({"requests": [legacy_row(r) for r in rows]})
        except DatabaseError:
            return self.error(503, "Unable to load requests.")


class AdminRequestDetailView(TeamLegacyView):
    @extend_schema(
        tags=["frontend-api"],
        summary="Team: update a request status and internal note",
        request=RequestUpdateSerializer,
        responses=OpenApiTypes.OBJECT,
    )
    def patch(self, request, reference):
        denied = self.team_gate(request, TEAM_ROLES)
        if denied:
            return denied
        if not origin_ok(request):
            return self.error(403, "Request origin not allowed")
        if not REFERENCE_RE.match(reference):
            return self.error(400, "Invalid reference")
        data, failure = self.body(request)
        if failure:
            return failure
        serializer = RequestUpdateSerializer(data=data)
        if not serializer.is_valid():
            return self.error(400, "Invalid status or note")
        req = Request.objects.filter(reference=reference).first()
        if req is None:
            return self.error(404, "Request not found")
        try:
            services.update_request(
                req,
                status=serializer.validated_data["status"],
                internal_note=serializer.validated_data["internalNote"],
                actor=actor_for(request),
            )
        except services.SlotTaken:
            return self.error(409, "This time is already requested by another customer.")
        except DatabaseError:
            return self.error(503, "Unable to update request.")
        return Response({"reference": reference, "status": serializer.validated_data["status"]})


def robots_txt(request):
    origin = (settings.PUBLIC_ORIGIN or request.build_absolute_uri("/").rstrip("/")).rstrip("/")
    text = (
        "User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /team\nDisallow: /status\n"
        "Disallow: /contact\nDisallow: /consultation\nDisallow: /start\nDisallow: /privacy\n"
        f"Disallow: /terms\nDisallow: /account\nSitemap: {origin}/sitemap.xml\n"
    )
    return HttpResponse(
        text, content_type="text/plain; charset=utf-8", headers={"Cache-Control": "public, max-age=3600"}
    )


def sitemap_xml(request):
    origin = (settings.PUBLIC_ORIGIN or request.build_absolute_uri("/").rstrip("/")).rstrip("/")
    urls = "\n".join(f"  <url><loc>{origin}{p}</loc></url>" for p in catalog.site_paths())
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + "\n</urlset>"
    )
    return HttpResponse(
        xml, content_type="application/xml; charset=utf-8", headers={"Cache-Control": "public, max-age=3600"}
    )
