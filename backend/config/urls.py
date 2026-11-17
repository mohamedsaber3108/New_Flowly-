from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse_lazy
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from apps.accounts.urls import auth_patterns, user_patterns
from apps.core.views import HealthView
from apps.leads import legacy_views
from apps.leads.urls import legacy_patterns, v1_patterns

api_v1 = [
    path("auth/", include(auth_patterns)),
    path("users/", include(user_patterns)),
    path("", include(v1_patterns)),
]

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("health/", HealthView.as_view(), name="health"),
    # Original frontend contract
    path("api/", include(legacy_patterns)),
    path("robots.txt", legacy_views.robots_txt),
    path("sitemap.xml", legacy_views.sitemap_xml),
    # Versioned API + docs
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # Password reset page (Django built-in views; link is emailed by the API)
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="account/password_reset_confirm.html", success_url=reverse_lazy("password-reset-complete")
        ),
        name="password-reset-confirm",
    ),
    path(
        "accounts/reset/done/",
        TemplateView.as_view(template_name="account/password_reset_complete.html"),
        name="password-reset-complete",
    ),
    # Account portal (login, register, dashboard, profile) - vanilla JS, talks to /api/v1
    path("account/", TemplateView.as_view(template_name="account/portal.html"), name="account-portal"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
