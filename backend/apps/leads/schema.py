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


class TeamJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.leads.auth.TeamJWTAuthentication"
    name = "teamJwtAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
