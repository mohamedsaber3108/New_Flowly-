"""django-unfold admin theme configuration (imported by settings/base.py)."""

from django.urls import reverse_lazy

UNFOLD = {
    "SITE_TITLE": "Flowly Admin",
    "SITE_HEADER": "Flowly Admin",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",
    "STYLES": [],
    "SCRIPTS": [],
    "COLORS": {
        "primary": {
            "50": "250 245 255",
            "100": "243 232 255",
            "200": "233 213 255",
            "300": "216 180 254",
            "400": "192 132 252",
            "500": "168 85 247",
            "600": "147 51 234",
            "700": "126 34 206",
            "800": "107 33 168",
            "900": "88 28 135",
            "950": "59 7 100",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
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
                ],
            },
        ],
    },
    "TABS": [],
}
