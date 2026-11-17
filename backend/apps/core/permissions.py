from rest_framework.permissions import SAFE_METHODS, BasePermission

TEAM_ROLES = ("owner", "staff")
READ_ROLES = ("owner", "staff", "viewer")


def has_role(user, roles):
    return bool(
        user
        and user.is_authenticated
        and not getattr(user, "is_deleted", False)
        and (user.is_superuser or getattr(user, "role", None) in roles)
    )


class IsOwnerOrStaff(BasePermission):
    """Full access for owner/staff roles (and superusers)."""

    message = "Team access is required."

    def has_permission(self, request, view):
        return has_role(request.user, TEAM_ROLES)


class IsTeamReadOrWrite(BasePermission):
    """Viewers may read; only owner/staff may modify."""

    message = "Team access is required."

    def has_permission(self, request, view):
        roles = READ_ROLES if request.method in SAFE_METHODS else TEAM_ROLES
        return has_role(request.user, roles)
