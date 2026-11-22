"""django-unfold admin theme configuration (imported by settings/base.py).

Colours follow the Flowly brand (frontend/app/globals.css): accent #ed541d is primary-500.
This Unfold version expects oklch() values.
"""

from django.urls import reverse_lazy

UNFOLD = {
    "SITE_TITLE": "Flowly Admin",
    "SITE_HEADER": "Flowly",
    "SITE_SUBHEADER": "Requests & operations",
    "SITE_URL": "/",
    "SITE_ICON": None,
    # Same icon as the public site, so browsers do not fall back to a missing /favicon.ico.
    "SITE_FAVICONS": [{"rel": "icon", "sizes": "any", "type": "image/svg+xml", "href": lambda request: "/favicon.svg"}],
    "SITE_SYMBOL": "water",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",
    "STYLES": [],
    "SCRIPTS": [],
    "COLORS": {
        "primary": {
            "50": "oklch(97.5% .015 45)",
            "100": "oklch(94.5% .035 45)",
            "200": "oklch(89% .07 44)",
            "300": "oklch(81% .12 42)",
            "400": "oklch(72% .17 40)",
            "500": "oklch(65% .2 38)",
            "600": "oklch(57% .19 36)",
            "700": "oklch(49% .165 35)",
            "800": "oklch(41% .135 35)",
            "900": "oklch(35% .105 35)",
            "950": "oklch(25% .075 35)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Overview",
                "items": [
                    {"title": "Dashboard", "icon": "dashboard", "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": "Requests",
                "items": [
                    {"title": "Requests", "icon": "inbox", "link": reverse_lazy("admin:leads_request_changelist")},
                    {
                        "title": "Appointments",
                        "icon": "event",
                        "link": reverse_lazy("admin:leads_appointment_changelist"),
                    },
                    {
                        "title": "Request events",
                        "icon": "history",
                        "link": reverse_lazy("admin:leads_requestevent_changelist"),
                    },
                    {
                        "title": "Assistant log",
                        "icon": "chat",
                        "link": reverse_lazy("admin:leads_assistantmessage_changelist"),
                    },
                ],
            },
            {
                "title": "People",
                "items": [
                    {"title": "Users", "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {
                        "title": "Email addresses",
                        "icon": "mail",
                        "link": reverse_lazy("admin:account_emailaddress_changelist"),
                    },
                ],
            },
        ],
    },
    "TABS": [],
}
