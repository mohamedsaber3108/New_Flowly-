from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.utils import mail_mode


class HealthView(APIView):
    """DB ping only. Used by load balancers and the deploy scripts."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes: list = []

    @extend_schema(tags=["system"], summary="Health check", responses={200: dict, 503: dict})
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # noqa: BLE001
            return Response(
                {
                    "success": False,
                    "data": {"status": "degraded", "database": "unavailable"},
                    "message": "Database unavailable.",
                    "errors": None,
                },
                status=503,
            )
        # "mail" says only whether mail is really sent by a server ("configured") or only logged ("console").
        return Response({"status": "ok", "database": "ok", "mail": mail_mode()})
