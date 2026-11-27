"""The current HTTP request, so audit.record() can add IP, client and request id without every caller passing them."""

import uuid
from contextvars import ContextVar

_request = ContextVar("audit_request", default=None)


class AuditContextMiddleware:
    """Remembers the request for this thread and gives every request an id (also sent back as X-Request-ID)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.META.get("HTTP_X_REQUEST_ID", "")
        request.audit_request_id = supplied[:64] if supplied.isprintable() and supplied else uuid.uuid4().hex
        token = _request.set(request)
        try:
            response = self.get_response(request)
        finally:
            _request.reset(token)
        response["X-Request-ID"] = request.audit_request_id
        return response


def current_request():
    return _request.get()
