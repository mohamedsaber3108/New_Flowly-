from django.urls import path

from . import views

auth_patterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", views.RefreshView.as_view(), name="auth-token-refresh"),
    path("password/reset/", views.PasswordResetView.as_view(), name="auth-password-reset"),
    path("password/reset/confirm/", views.PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("verify-email/<str:key>/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-verification/", views.ResendVerificationView.as_view(), name="auth-resend-verification"),
    path("social/google/", views.GoogleStartView.as_view(), name="auth-google"),
    path("social/google/callback/", views.GoogleCallbackView.as_view(), name="auth-google-callback"),
]

user_patterns = [
    path("me/", views.MeView.as_view(), name="user-me"),
    path("me/avatar/", views.AvatarView.as_view(), name="user-avatar"),
    path("me/change-password/", views.ChangePasswordView.as_view(), name="user-change-password"),
]
