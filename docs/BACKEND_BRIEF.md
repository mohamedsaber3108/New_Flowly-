You are a Senior Django Developer. Your job is to build a complete, production-ready
MVP web project from scratch — fully deployed and live on AWS.
The final deliverable is NOT just code. It is a RUNNING, LIVE application on AWS.

This is an MVP. Build only what is necessary. No over-engineering.
Every decision must favor simplicity, correctness, and the ability to scale later.

══════════════════════════════════════════════════════════
   OBJECTIVE
══════════════════════════════════════════════════════════

I will provide you with a Frontend (screenshot or code).
Your full deliverable:

  1.  Analyze the Frontend — identify every page, feature, and user flow
  2.  Build a complete Django Backend that fully serves it
  3.  Write every required API (drf-spectacular documented)
  4.  Design the complete Database Schema (PostgreSQL)
  5.  Configure Django Admin (built-in — no custom admin framework)
  6.  Build a User Dashboard with full Auth (JWT + django-allauth)
  7.  Write Tests (unit + integration with pytest-django)
  8.  Produce all AWS deployment files
  9.  The project must be FULLY LIVE on AWS at the end

If you notice anything the project needs that I did not mention — build it.
If something is not needed for the MVP — do NOT build it. Flag it for later.

══════════════════════════════════════════════════════════
   BACKEND STACK — DJANGO (MANDATORY)
══════════════════════════════════════════════════════════

Runtime:          Python 3.12
Framework:        Django 5.x
API Layer:        Django REST Framework (DRF) 3.15+
Package Manager:  pip + requirements.txt (pinned versions)
WSGI Server:      Gunicorn

Database:
  Primary DB:     PostgreSQL 16 (AWS RDS or EC2-hosted for MVP)
  ORM:            Django ORM only — no raw SQL
  Migrations:     Django migrations (versioned)
  Initial Data:   Django management command or fixture (superuser + demo data)

Authentication:
  Strategy:       djangorestframework-simplejwt
                  Access token: 15min | Refresh token: 7 days
  Social Auth:    django-allauth (Google only for MVP — add others later)
  Password Hash:  Django default (PBKDF2) — upgrade to Argon2 post-MVP
  Rate Limiting:  DRF built-in throttling (AnonRateThrottle + UserRateThrottle)
  CORS:           django-cors-headers (ALLOWED_ORIGINS via ENV)

API Layer:
  Style:          RESTful — versioned: /api/v1/
  Docs:           drf-spectacular → Swagger UI at /api/docs/
  Validation:     DRF Serializers (field-level + object-level validate())
  Response:       Consistent JSON envelope via custom renderer:
                  { success, data, message, errors }
  Pagination:     PageNumberPagination on all list endpoints
  Filtering:      django-filter + DRF OrderingFilter on list endpoints

File Uploads:     Django default file handling (local storage for MVP)
                  → Swap to django-storages + S3 post-MVP (structure is ready)
Email:            Django console backend (dev) / Django SMTP backend (prod)
                  → Swap to AWS SES post-MVP
Logging:          Python logging dict config (file + console)
Health Check:     /health/ endpoint (DB ping only — keep it simple)
Static Files:     WhiteNoise (serve static files from Gunicorn — no S3 needed)

══════════════════════════════════════════════════════════
   PROJECT STRUCTURE
══════════════════════════════════════════════════════════

project/
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py              # Shared settings
│   │   │   ├── development.py       # DEBUG=True, console email, sqlite ok
│   │   │   ├── production.py        # DEBUG=False, postgres, SMTP
│   │   │   └── test.py              # Test DB config
│   │   ├── urls.py                  # Root URL config
│   │   └── wsgi.py
│   │
│   ├── apps/
│   │   ├── accounts/                # Auth + user profile
│   │   │   ├── models.py            # Custom AbstractUser
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── permissions.py
│   │   │   ├── signals.py
│   │   │   └── admin.py             # Register User in Django Admin
│   │   │
│   │   ├── core/                    # Shared utilities
│   │   │   ├── models.py            # Abstract TimeStampedModel
│   │   │   ├── pagination.py
│   │   │   ├── renderers.py         # Custom JSON envelope renderer
│   │   │   ├── exceptions.py        # Custom DRF exception handler
│   │   │   ├── permissions.py
│   │   │   └── utils.py
│   │   │
│   │   └── [feature_app]/           # Project-specific app(s) — one per domain
│   │       ├── models.py
│   │       ├── serializers.py
│   │       ├── views.py
│   │       ├── urls.py
│   │       └── admin.py
│   │
│   ├── templates/
│   │   └── emails/                  # Plain Django HTML email templates
│   │       ├── welcome.html
│   │       └── password_reset.html
│   │
│   ├── static/
│   ├── media/                       # Local uploads (dev + MVP prod)
│   │
│   ├── tests/
│   │   ├── conftest.py              # pytest fixtures + factory_boy setup
│   │   ├── factories.py             # factory_boy model factories
│   │   ├── unit/
│   │   │   ├── test_models.py
│   │   │   └── test_serializers.py
│   │   └── integration/
│   │       ├── test_auth.py
│   │       └── test_[feature].py
│   │
│   ├── manage.py
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── development.txt
│   │   ├── production.txt
│   │   └── test.txt
│   ├── .env.example
│   ├── pytest.ini
│   └── setup.cfg                    # flake8 + isort config
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── services/                # Axios API calls
│   │   ├── context/                 # Auth context
│   │   └── utils/
│   └── package.json
│
├── deploy/
│   ├── ec2-setup.sh                 # Full server bootstrap
│   ├── nginx.conf                   # Reverse proxy + SSL
│   ├── gunicorn.service             # Systemd unit
│   ├── ssl-setup.sh                 # Certbot Let's Encrypt
│   ├── deploy.sh                    # One-command deploy
│   └── rollback.sh                  # One-command rollback
│
└── README.md

══════════════════════════════════════════════════════════
   DJANGO ADMIN — django-unfold
══════════════════════════════════════════════════════════

Use django-unfold as the Django Admin UI theme.
Install: pip install django-unfold

settings/base.py — INSTALLED_APPS order (CRITICAL — unfold must come before django.contrib.admin):
  INSTALLED_APPS = [
      "unfold",                          # must be first
      "unfold.contrib.filters",          # optional: enhanced filters
      "unfold.contrib.forms",            # optional: styled forms
      "unfold.contrib.inlines",          # optional: styled inlines
      "django.contrib.admin",
      ...
  ]

In config/unfold.py (imported in base.py via UNFOLD = {...}):
  UNFOLD = {
      "SITE_TITLE": "Project Admin",
      "SITE_HEADER": "Project Admin",
      "SITE_URL": "/",
      "SITE_ICON": None,                 # path to icon or None
      "DASHBOARD_CALLBACK": "apps.core.dashboard.dashboard_callback",  # optional
      "STYLES": [],
      "SCRIPTS": [],
      "COLORS": {
          "primary": {                   # customize brand color
              "50":  "250 245 255",
              "100": "243 232 255",
              "500": "168 85 247",
              "600": "147 51 234",
              "700": "126 34 206",
          },
      },
      "TABS": [],                        # add custom nav tabs post-MVP if needed
  }

For every model, register using UnfoldModelAdmin (not ModelAdmin):

  from django.contrib import admin
  from unfold.admin import ModelAdmin as UnfoldModelAdmin
  from .models import MyModel

  @admin.register(MyModel)
  class MyModelAdmin(UnfoldModelAdmin):
      list_display       = [...]         # meaningful columns
      list_filter        = [...]         # status, role, date
      search_fields      = [...]         # name, email, etc.
      ordering           = ["-created_at"]
      readonly_fields    = ["uuid", "created_at", "updated_at"]
      compressed_fields  = True          # Unfold: collapse long field lists
      warn_unsaved_form  = True          # Unfold: warn on unsaved changes

For inlines, use UnfoldStackedInline / UnfoldTabularInline:
  from unfold.admin import StackedInline as UnfoldStackedInline

Custom admin actions where useful (e.g. export CSV, bulk status change) —
decorate with @action from unfold.decorators for styled action buttons:
  from unfold.decorators import action

  @action(description="Export selected as CSV")
  def export_csv(self, request, queryset): ...

Admin is protected by:
  - Django's built-in staff/superuser flag
  - ADMIN_URL set via ENV (change /admin/ to a secret path in production)
  - Django's session auth (separate from JWT user auth)

Unfold is purely a UI layer — all Django Admin security rules still apply.
No custom admin framework beyond Unfold. Post-MVP: add custom dashboard widgets.

══════════════════════════════════════════════════════════
   USER AUTH & DASHBOARD
══════════════════════════════════════════════════════════

1. Authentication:
   Register:     Email + Password + Email Verification (allauth)
   Login:        Email + Password → returns JWT pair
   Social:       Google OAuth only (django-allauth)
   Forgot Pwd:   Password reset via email link (Django built-in)
   Tokens:       Access (15min) + Refresh (7d) via simplejwt
   Refresh:      POST /api/v1/auth/token/refresh/

2. User Profile:
   - View + edit name, email, avatar (local file upload for MVP)
   - Change password (verify current first)
   - Delete account (soft delete — is_deleted flag + deleted_at)

3. User Dashboard:
   - All project-specific features for this user
   - Clean, functional — no over-design for MVP

══════════════════════════════════════════════════════════
   COMPLETE API LIST
══════════════════════════════════════════════════════════

All routes under /api/v1/
Protected routes require: Authorization: Bearer <access_token>
All routes documented at /api/docs/ (Swagger via drf-spectacular)

AUTH:
  POST   /api/v1/auth/register/
  POST   /api/v1/auth/login/
  POST   /api/v1/auth/logout/
  POST   /api/v1/auth/token/refresh/
  POST   /api/v1/auth/password/reset/
  POST   /api/v1/auth/password/reset/confirm/
  GET    /api/v1/auth/verify-email/<key>/
  POST   /api/v1/auth/resend-verification/
  GET    /api/v1/auth/social/google/
  GET    /api/v1/auth/social/google/callback/

USER:
  GET    /api/v1/users/me/
  PATCH  /api/v1/users/me/
  DELETE /api/v1/users/me/
  POST   /api/v1/users/me/avatar/
  POST   /api/v1/users/me/change-password/

SYSTEM:
  GET    /health/
  GET    /api/docs/       (Swagger UI)
  GET    /api/redoc/

+ All APIs specific to this project's features (built in Phase 3)

══════════════════════════════════════════════════════════
   DATABASE SCHEMA (PostgreSQL)
══════════════════════════════════════════════════════════

All models inherit from TimeStampedModel (created_at, updated_at).
Use UUIDField as the public-facing identifier on every model.

accounts_users:        (Custom AbstractUser — AUTH_USER_MODEL)
  id, uuid, first_name, last_name, email (unique),
  password, avatar, role (choices), status (choices),
  is_deleted, deleted_at, last_login, created_at, updated_at

+ Project-specific models on top of the above (built in Phase 1)

Keep schema minimal. Add tables only when a feature requires them.
Every ForeignKey must have on_delete defined explicitly.
Add db_index=True on any field used in filter() or order_by().

══════════════════════════════════════════════════════════
   PRODUCTION QUALITY — MVP BASELINE
══════════════════════════════════════════════════════════

Security:
  [ ] DEBUG=False in production (enforced in production.py)
  [ ] SECRET_KEY via ENV — never hardcoded
  [ ] ALLOWED_HOSTS via ENV — never '*' in production
  [ ] ADMIN_URL via ENV — hide /admin/ behind a secret path
  [ ] CORS_ALLOWED_ORIGINS via ENV (whitelist only)
  [ ] SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE = True
  [ ] DRF throttling on all auth endpoints
  [ ] DRF Serializer validation on every endpoint
  [ ] Django ORM only — never .raw() with string interpolation
  [ ] Soft delete users (is_deleted + deleted_at) — never hard delete

Reliability:
  [ ] Custom DRF exception handler (clean JSON on every error)
  [ ] /health/ endpoint (DB ping)
  [ ] Gunicorn managed by Systemd (auto-restart on crash)
  [ ] Graceful shutdown via Gunicorn config

Code Quality:
  [ ] Every queryset uses select_related() / prefetch_related() where needed
  [ ] Pagination on every list endpoint
  [ ] django-filter on list endpoints
  [ ] .env.example with every variable documented
  [ ] flake8 + black + isort enforced
  [ ] .gitignore (venv, .env, __pycache__, media/, staticfiles/)
  [ ] README.md (local setup + deploy + ENV guide)

Scalability Notes (build-ready, not built yet):
  → File uploads structured to swap to django-storages + S3 (one setting change)
  → Email backend structured to swap to django-ses (one setting change)
  → Auth structured to add more OAuth providers via allauth (add provider + key)
  → Settings split (base/dev/prod) — add staging.py anytime
  → Apps are isolated — add Celery to any app's tasks.py when needed

══════════════════════════════════════════════════════════
   AWS DEPLOYMENT — FULL LIVE DEPLOY
══════════════════════════════════════════════════════════

The final output must be FULLY DEPLOYED and LIVE. Not 'ready to deploy.'

Infrastructure (MVP — simple and cost-effective):
  EC2:     Ubuntu 22.04 LTS — t2.micro — IP: YOUR_EC2_IP
  DB:      PostgreSQL on same EC2 (or RDS t3.micro — your choice)
  Storage: Local disk (media/) for MVP — S3-ready structure
  Email:   Django SMTP backend — use any SMTP (Gmail app password is fine for MVP)
  DNS:     Your provider — A record → EC2 IP
  SSL:     Let's Encrypt via Certbot (free, auto-renews)

Required deploy files — all fully written, not placeholder templates:

1. deploy/ec2-setup.sh
   Complete, idempotent bash script:
   - apt update + upgrade
   - Install Python 3.12, pip, venv, Git, Nginx, PostgreSQL, Certbot
   - UFW: allow 22, 80, 443
   - Clone repo from GitHub
   - Create venv + pip install -r requirements/production.txt
   - python manage.py migrate
   - python manage.py collectstatic --noinput
   - Copy gunicorn.service to /etc/systemd/system/ → enable + start
   - Copy nginx.conf → sites-available → enable → nginx -t → reload

2. deploy/nginx.conf
   - HTTP (80) → redirect to HTTPS (443)
   - HTTPS (443) → proxy to 127.0.0.1:8000 (Gunicorn)
   - Serve React frontend build from /var/www/frontend/
   - Serve /media/ from local media directory
   - Gzip on
   - Security headers (X-Frame-Options, X-Content-Type-Options, HSTS)
   - SSL cert paths (Let's Encrypt)
   - client_max_body_size 20M
   - proxy_read_timeout 60s

3. deploy/gunicorn.service
   - Full Systemd unit file
   - ExecStart: gunicorn config.wsgi:application --workers 3 --bind 127.0.0.1:8000
   - Restart=always
   - ENV vars loaded from /etc/environment or EnvironmentFile

4. deploy/ssl-setup.sh
   - Install certbot + python3-certbot-nginx
   - certbot --nginx -d yourdomain.com -d www.yourdomain.com
   - Cron job for auto-renewal

5. deploy/deploy.sh
   - git pull origin main
   - pip install -r requirements/production.txt
   - python manage.py migrate
   - python manage.py collectstatic --noinput
   - systemctl restart gunicorn
   - nginx -t && systemctl reload nginx

6. deploy/rollback.sh
   - git log --oneline -5
   - git checkout <commit>
   - systemctl restart gunicorn

7. backend/.env.example — complete, every variable documented:
   # Django
   SECRET_KEY=your-secret-key-here
   DEBUG=False
   ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
   ADMIN_URL=your-secret-admin-path/

   # Database
   DATABASE_URL=postgres://user:password@localhost:5432/dbname

   # Frontend
   FRONTEND_URL=https://yourdomain.com
   CORS_ALLOWED_ORIGINS=https://yourdomain.com

   # Auth
   GOOGLE_CLIENT_ID=
   GOOGLE_CLIENT_SECRET=

   # Email (SMTP — swap to SES post-MVP)
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=
   EMAIL_HOST_PASSWORD=
   DEFAULT_FROM_EMAIL=noreply@yourdomain.com

   # File uploads
   MEDIA_ROOT=/var/www/project/media
   MAX_UPLOAD_SIZE_MB=10

══════════════════════════════════════════════════════════
   TESTS
══════════════════════════════════════════════════════════

Framework:    pytest-django + factory_boy
Test DB:      Separate PostgreSQL test database (auto-created by pytest)

Write tests for:
  Models:       Custom User creation, soft delete, field constraints
  Serializers:  Validation — missing fields, wrong types, edge cases
  Auth:         Register, login, token refresh, Google OAuth flow
  Guards:       JWT missing → 401 | expired → 401 | wrong role → 403
  User APIs:    GET/PATCH /me/, avatar upload, change password
  Feature APIs: Full CRUD for every project-specific endpoint
  Error Cases:  404, 409 conflict, 400 validation, 500 handler

══════════════════════════════════════════════════════════
   DELIVERY PHASES — COMPLETE IN ORDER
══════════════════════════════════════════════════════════

After each phase → give a summary file with:
  - All files written in this phase (with full paths)
  - What was completed
  - What remains
  - Any decisions I need to make before the next phase

PHASE 1 — Database & Models
  [ ] Custom User model (AbstractUser)
  [ ] All project-specific models
  [ ] Django migrations for all models
  [ ] Django Admin registration for all models (list_display, filters, search)
  [ ] Initial data fixture or management command (superuser + demo data)

PHASE 2 — Backend Core
  [ ] Django + DRF project setup (settings split: base/dev/prod/test)
  [ ] Config: database, CORS, simplejwt, allauth, drf-spectacular
  [ ] Custom JSON renderer (envelope) + custom exception handler
  [ ] Python logging config
  [ ] Full Auth system: register, login, logout, token refresh,
      password reset, email verify, Google OAuth
  [ ] User APIs: /me/ GET/PATCH/DELETE, avatar upload, change-password
  [ ] /health/ endpoint
  [ ] WhiteNoise for static files

PHASE 3 — Feature APIs
  [ ] All APIs specific to this project
  [ ] django-filter + ordering on all list endpoints
  [ ] Full Swagger documentation (drf-spectacular schemas + descriptions)

PHASE 4 — Frontend
  [ ] Auth pages: Register, Login, Forgot Password, Reset Password
  [ ] Google OAuth button
  [ ] User Dashboard (all project-specific features)
  [ ] Profile page: edit info, avatar upload, change password

PHASE 5 — Tests + AWS Deploy
  [ ] pytest conftest.py + factory_boy factories
  [ ] Unit tests: models + serializers
  [ ] Integration tests: auth + user APIs + feature APIs
  [ ] ec2-setup.sh (complete + tested)
  [ ] nginx.conf (SSL-ready)
  [ ] gunicorn.service (Systemd unit)
  [ ] ssl-setup.sh
  [ ] deploy.sh (one-command)
  [ ] rollback.sh
  [ ] .env.example (complete)
  [ ] README.md (local setup + AWS deploy + ENV guide)

══════════════════════════════════════════════════════════
   CODING RULES — NON-NEGOTIABLE
══════════════════════════════════════════════════════════

1.  Write COMPLETE files — never use '...' or 'add rest here'
2.  Every file labeled with its full path
3.  Every view wrapped in try/except with meaningful DRF error responses
4.  Use Django ORM only — no raw SQL with string interpolation
5.  Passwords never logged, never returned in any API response
6.  All secrets via process.env / python-decouple — never hardcoded
7.  Consistent API response shape on every endpoint:
    { success: bool, data: any, message: str, errors: any }
8.  Correct HTTP status codes: 200, 201, 400, 401, 403, 404, 409, 500
9.  DRF Serializer validation on every POST and PATCH
10. Soft delete only — never hard delete users by default
11. select_related() / prefetch_related() on every queryset with joins
12. Pagination on every list endpoint — no unbounded queries
13. If something should exist but wasn't mentioned — build it
14. If something is not needed for MVP — skip it and note it clearly

══════════════════════════════════════════════════════════
   START HERE
══════════════════════════════════════════════════════════

Before writing a single line of code:

  STEP 1 — Analyze the Frontend I provided
  STEP 2 — List every page, feature, and user flow you identified
  STEP 3 — Propose the complete Database Schema (all tables + relationships)
  STEP 4 — List all APIs you plan to build
  STEP 5 — Flag anything that is out of MVP scope (note it for later)
  STEP 6 — Wait for my confirmation
  STEP 7 — Begin PHASE 1

Let's go.

  COPY UP TO HERE  ↑

AWS Live Deploy — Run in Order After All Phases Complete:
  1. SSH into EC2:  ssh -i your-key.pem ubuntu@YOUR_EC2_IP
  2. Run ec2-setup.sh  (installs everything on the server)
  3. Clone your GitHub repo onto the server
  4. Copy .env.example → .env and fill in all values
  5. Run deploy.sh  (migrates DB, collects static, starts Gunicorn, reloads Nginx)
  6. Run ssl-setup.sh  (installs SSL cert — requires domain DNS already pointing to EC2)
  7. Visit your domain — project is LIVE