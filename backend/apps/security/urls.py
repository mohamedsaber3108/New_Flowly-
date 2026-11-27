from django.urls import path

from . import views

# /api/v1/auth/mfa/...
api_patterns = [
    path("enroll/", views.EnrollApiView.as_view(), name="mfa-enroll"),
    path("confirm/", views.ConfirmApiView.as_view(), name="mfa-confirm"),
]
