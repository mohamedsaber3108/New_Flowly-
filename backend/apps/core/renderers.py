"""JSON envelope renderer: every /api/v1 response is { success, data, message, errors }."""

from rest_framework.renderers import JSONRenderer

ENVELOPE_KEYS = {"success", "data", "message", "errors"}


class EnvelopeJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get("response")
        status_code = getattr(response, "status_code", 200)
        if isinstance(data, dict) and set(data.keys()) == ENVELOPE_KEYS:
            payload = data  # already shaped by the exception handler
        elif status_code >= 400:
            payload = {"success": False, "data": None, "message": "Request failed.", "errors": data}
        else:
            message = ""
            if isinstance(data, dict) and set(data.keys()) == {"message", "data"}:
                message, data = data["message"], data["data"]
            payload = {"success": True, "data": data, "message": message, "errors": None}
        return super().render(payload, accepted_media_type, renderer_context)


class LegacyJSONRenderer(JSONRenderer):
    """Plain JSON with the hardening headers the original frontend API used."""
