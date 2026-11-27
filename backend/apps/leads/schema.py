"""OpenAPI descriptions for the custom team authentication classes."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AdminTokenScheme(OpenApiAuthenticationExtension):
    target_class = "apps.leads.auth.AdminTokenAuthentication"
    name = "adminToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Shared ADMIN_TOKEN (min 32 chars) used by the original /team console. "
                "Ignored unless ALLOW_SHARED_ADMIN_TOKEN=True."
            ),
        }


class CookieJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.session_cookie.CookieJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Customers: bearer JWT. Team accounts: an httpOnly cookie set at sign-in; a request that changes data "
                "also needs the X-CSRFToken header."
            ),
        }


class TeamJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.leads.auth.TeamJWTAuthentication"
    name = "teamJwtAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
