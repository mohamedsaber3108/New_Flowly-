"""Manual scoped throttling for views that must throttle *after* an idempotency check."""

from rest_framework.throttling import SimpleRateThrottle

from .utils import client_ip


class _ScopeThrottle(SimpleRateThrottle):
    def __init__(self, scope):
        self.scope = scope
        super().__init__()

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_ip(request)}


def allow_request(request, scope) -> bool:
    """Count one hit for this client in the scope; False when the limit is exceeded."""
    return _ScopeThrottle(scope).allow_request(request, None)
