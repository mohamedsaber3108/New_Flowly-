"""Exception handlers: clean JSON on every error, never a stack trace."""

import logging

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Conflict with the current state of the resource."
    default_code = "conflict"


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable."
    default_code = "unavailable"


def flatten_errors(detail):
    """Turn DRF error detail into a short human message."""
    if isinstance(detail, dict):
        parts = []
        for key, value in detail.items():
            text = flatten_errors(value)
            parts.append(text if key in ("detail", "non_field_errors") else f"{key}: {text}")
        return " ".join(parts)
    if isinstance(detail, (list, tuple)):
        return " ".join(flatten_errors(item) for item in detail)
    return str(detail)


def envelope(message, errors=None, status_code=400):
    return Response(
        {"success": False, "data": None, "message": message, "errors": errors},
        status=status_code,
    )


def envelope_exception_handler(exc, context):
    if isinstance(exc, Http404):
        return envelope("Not found.", None, 404)
    if isinstance(exc, PermissionDenied):
        return envelope("You do not have permission to perform this action.", None, 403)

    response = exception_handler(exc, context)
    if response is not None:
        data = response.data
        if isinstance(exc, ValidationError):
            message = "Validation failed." if isinstance(data, dict) else flatten_errors(data)
            return envelope(message, data, response.status_code)
        if isinstance(exc, Throttled):
            return envelope("Too many requests. Please try again later.", {"retry_after": exc.wait}, 429)
        message = flatten_errors(data.get("detail", data)) if isinstance(data, dict) else flatten_errors(data)
        return envelope(message, None, response.status_code)

    if isinstance(exc, DatabaseError):
        logger.exception("Database error in %s", context.get("view").__class__.__name__)
        return envelope("Storage is temporarily unavailable.", None, 503)
    logger.exception("Unhandled error in %s", context.get("view").__class__.__name__)
    return envelope("An unexpected error occurred.", None, 500)


def legacy_exception_handler(exc, context):
    """Original frontend contract: errors are { error: "message" }."""
    if isinstance(exc, Http404):
        return Response({"error": "Not found"}, status=404)
    response = exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, Throttled):
            return Response({"error": "Too many requests. Please try again later."}, status=429)
        data = response.data
        detail = data.get("detail", data) if isinstance(data, dict) else data
        return Response({"error": flatten_errors(detail)}, status=response.status_code)
    logger.exception("Unhandled error in %s", context.get("view").__class__.__name__)
    return Response({"error": "Internal server error"}, status=500)
