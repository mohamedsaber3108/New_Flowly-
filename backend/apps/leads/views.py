"""Versioned API (/api/v1/...). All responses use the {success, data, message, errors} envelope."""

import logging

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import Http404
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import Conflict, envelope
from apps.core.permissions import IsTeamReadOrWrite

from . import assistant as assistant_service
from . import intake, services
from .auth import TEAM_AUTHENTICATION, actor_for, optional_user
from .models import Appointment, Request
from .serializers import (
    AssistantSerializer,
    MyRequestDetailSerializer,
    MyRequestSerializer,
    RequestCreateSerializer,
    RequestLookupSerializer,
    TeamRequestDetailSerializer,
    TeamRequestSerializer,
    TeamRequestUpdateSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()

SubmitResponse = inline_serializer(
    "SubmitResponse",
    {
        "reference": serializers.CharField(),
        "status": serializers.CharField(),
        "appointment": serializers.DictField(allow_null=True, required=False),
    },
)


def _intake_failure(exc: intake.IntakeError):
    return envelope(exc.message, exc.errors, exc.status)


class PublicAPIView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]


class SubmitRequestView(PublicAPIView):
    @extend_schema(
        tags=["requests"],
        summary="Submit a discovery, consultation or contact request",
        description="Idempotent on requestKey. A bearer token is optional; when present the request "
        "is linked to the signed-in account.",
        request=RequestCreateSerializer,
        responses={201: SubmitResponse, 200: SubmitResponse},
    )
    def post(self, request):
        try:
            code, body = intake.submit_request(request, request.data, user=optional_user(request))
        except intake.IntakeError as exc:
            return _intake_failure(exc)
        message = "Request received." if code == 201 else "Request already received."
        return Response({"message": message, "data": body}, status=code)


class LookupRequestView(PublicAPIView):
    @extend_schema(
        tags=["requests"],
        summary="Track a request by reference and email",
        request=RequestLookupSerializer,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        try:
            return Response(intake.lookup_request(request, request.data))
        except intake.IntakeError as exc:
            return _intake_failure(exc)


class AvailabilityView(PublicAPIView):
    @extend_schema(
        tags=["requests"],
        summary="Busy consultation times for a date (Africa/Cairo)",
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD, weekdays Sun-Thu, within 90 days")],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        try:
            return Response(intake.availability(request.query_params.get("date", "")))
        except intake.IntakeError as exc:
            return _intake_failure(exc)


class AssistantView(PublicAPIView):
    @extend_schema(tags=["assistant"], summary="Assistant mode: ai or guide", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        return Response({"mode": "ai" if assistant_service.configured() else "guide"})

    @extend_schema(
        tags=["assistant"],
        summary="Ask the service-discovery assistant",
        request=AssistantSerializer,
        responses={200: OpenApiTypes.OBJECT},
    )
    def post(self, request):
        try:
            return Response(intake.assistant_reply(request, request.data, user=optional_user(request)))
        except intake.IntakeError as exc:
            return _intake_failure(exc)


# --- Customer dashboard -----------------------------------------------------


def my_requests_queryset(user):
    """Requests linked to the account, plus anonymous ones made with the account's verified email."""
    verified = EmailAddress.objects.filter(user=user, verified=True).values_list("email", flat=True)
    email_q = Q()
    for address in verified:
        email_q |= Q(email__iexact=address, user__isnull=True)
    return Request.objects.filter(Q(user=user) | email_q).prefetch_related("appointments")


class MyRequestFilter(filters.FilterSet):
    class Meta:
        model = Request
        fields = {"status": ["exact"], "kind": ["exact"], "audience": ["exact"], "created_at": ["gte", "lte"]}


class MyRequestListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MyRequestSerializer
    filterset_class = MyRequestFilter
    ordering_fields = ["created_at", "status"]
    ordering = ["-created_at"]
    search_fields = ["reference", "organization"]

    @extend_schema(tags=["dashboard"], summary="My requests (paginated)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Request.objects.none()
        return my_requests_queryset(self.request.user)


class MyRequestDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MyRequestDetailSerializer
    lookup_field = "reference"

    @extend_schema(tags=["dashboard"], summary="One of my requests, with its timeline")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Request.objects.none()
        return my_requests_queryset(self.request.user).prefetch_related("events")


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["dashboard"], summary="Customer dashboard summary", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        qs = my_requests_queryset(request.user)
        by_status = {row["status"]: row["n"] for row in qs.values("status").annotate(n=Count("id"))}
        upcoming = (
            Appointment.objects.filter(request__in=qs, status__in=["provisional", "confirmed"])
            .order_by("date", "time")
            .select_related("request")
            .first()
        )
        return Response(
            {
                "total_requests": sum(by_status.values()),
                "by_status": by_status,
                "open_requests": sum(n for s, n in by_status.items() if s not in ("completed", "declined", "canceled")),
                "next_appointment": (
                    None
                    if upcoming is None
                    else {
                        "reference": upcoming.request.reference,
                        "date": upcoming.date.isoformat(),
                        "time": upcoming.time,
                        "timezone": upcoming.timezone,
                        "status": upcoming.status,
                    }
                ),
                "recent": MyRequestSerializer(qs.order_by("-created_at")[:5], many=True).data,
            }
        )


# --- Team -------------------------------------------------------------------


class TeamRequestFilter(filters.FilterSet):
    created_from = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    created_to = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    has_appointment = filters.BooleanFilter(method="filter_has_appointment")

    class Meta:
        model = Request
        fields = ["status", "kind", "audience", "language", "assigned_to"]

    def filter_has_appointment(self, queryset, name, value):
        return queryset.filter(appointments__isnull=not value).distinct()


class TeamRequestListView(generics.ListAPIView):
    authentication_classes = TEAM_AUTHENTICATION
    permission_classes = [IsTeamReadOrWrite]
    serializer_class = TeamRequestSerializer
    filterset_class = TeamRequestFilter
    search_fields = ["reference", "name", "email", "organization"]
    ordering_fields = ["created_at", "updated_at", "status", "name"]
    ordering = ["-created_at"]
    queryset = Request.objects.select_related("assigned_to").prefetch_related("appointments")

    @extend_schema(tags=["team"], summary="Team: list requests (filter, search, order, paginate)")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class TeamRequestDetailView(APIView):
    authentication_classes = TEAM_AUTHENTICATION
    permission_classes = [IsTeamReadOrWrite]

    def get_object(self, reference):
        try:
            return (
                Request.objects.select_related("assigned_to")
                .prefetch_related("appointments", "events__actor")
                .get(reference=reference)
            )
        except Request.DoesNotExist:
            raise Http404

    @extend_schema(
        tags=["team"], summary="Team: request detail with event history", responses={200: TeamRequestDetailSerializer}
    )
    def get(self, request, reference):
        return Response(TeamRequestDetailSerializer(self.get_object(reference)).data)

    @extend_schema(
        tags=["team"],
        summary="Team: change status, internal note or assignee",
        request=TeamRequestUpdateSerializer,
        responses={200: TeamRequestDetailSerializer},
    )
    def patch(self, request, reference):
        req = self.get_object(reference)
        serializer = TeamRequestUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assign = "assigned_to" in data
        assignee = None
        if assign and data["assigned_to"]:
            assignee = User.objects.filter(
                email__iexact=data["assigned_to"],
                is_active=True,
                is_deleted=False,
                role__in=["owner", "staff"],
            ).first()
            if assignee is None:
                return envelope("Validation failed.", {"assigned_to": ["No active team member has this email."]}, 400)
        try:
            services.update_request(
                req,
                status=data.get("status"),
                internal_note=data.get("internal_note"),
                assigned_to=assignee,
                assign=assign,
                actor=actor_for(request),
            )
        except services.SlotTaken:
            raise Conflict("This time is already requested by another customer.")
        return Response(
            {"message": "Request updated.", "data": TeamRequestDetailSerializer(self.get_object(reference)).data}
        )


class TeamStatsView(APIView):
    authentication_classes = TEAM_AUTHENTICATION
    permission_classes = [IsTeamReadOrWrite]

    @extend_schema(tags=["team"], summary="Team: pipeline counters", responses={200: OpenApiTypes.OBJECT})
    def get(self, request):
        by_status = {r["status"]: r["n"] for r in Request.objects.values("status").annotate(n=Count("id"))}
        by_kind = {r["kind"]: r["n"] for r in Request.objects.values("kind").annotate(n=Count("id"))}
        return Response(
            {
                "total": sum(by_status.values()),
                "by_status": by_status,
                "by_kind": by_kind,
                "active_appointments": Appointment.objects.filter(status__in=["provisional", "confirmed"]).count(),
            }
        )
