from django.urls import path

from . import legacy_views, views

# /api/* — original frontend contract (raw JSON)
legacy_patterns = [
    path("health", legacy_views.HealthView.as_view(), name="legacy-health"),
    path("requests", legacy_views.RequestsView.as_view(), name="legacy-requests"),
    path("availability", legacy_views.AvailabilityView.as_view(), name="legacy-availability"),
    path("request-status", legacy_views.RequestStatusView.as_view(), name="legacy-request-status"),
    path("assistant", legacy_views.AssistantView.as_view(), name="legacy-assistant"),
    path("admin/requests", legacy_views.AdminRequestsView.as_view(), name="legacy-admin-requests"),
    path("admin/requests/<str:reference>", legacy_views.AdminRequestDetailView.as_view(), name="legacy-admin-request"),
]

# /api/v1/* — versioned, enveloped
v1_patterns = [
    path("requests/", views.SubmitRequestView.as_view(), name="request-submit"),
    path("requests/lookup/", views.LookupRequestView.as_view(), name="request-lookup"),
    path("requests/mine/", views.MyRequestListView.as_view(), name="request-mine"),
    path("requests/mine/<str:reference>/", views.MyRequestDetailView.as_view(), name="request-mine-detail"),
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("assistant/", views.AssistantView.as_view(), name="assistant"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("admin/requests/", views.TeamRequestListView.as_view(), name="team-requests"),
    path("admin/requests/<str:reference>/", views.TeamRequestDetailView.as_view(), name="team-request-detail"),
    path("admin/stats/", views.TeamStatsView.as_view(), name="team-stats"),
]
