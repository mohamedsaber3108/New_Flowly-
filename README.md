# Flowly

Bilingual (EN/AR) AI, software and automation services website with a Django backend.

```
New_Flowly/
├── backend/    Django 5.2 + DRF API, Unfold admin, JWT + allauth auth, pytest suite
├── frontend/   Existing React site (unchanged) - prebuilt in frontend/ec2-dist/public
└── deploy/     EC2 scripts: ec2-setup.sh, nginx.conf, gunicorn.service, ssl-setup.sh, deploy.sh, rollback.sh
```

The React app is used **as is**. Its original API contract (`/api/requests`, `/api/availability`,
`/api/request-status`, `/api/assistant`, `/api/admin/requests`, `/api/health`, `/robots.txt`,
`/sitemap.xml`) is implemented by Django with identical request and response shapes, so the
Intake wizard, status page, assistant and `/team` console work without code changes.

## What the backend provides

| Area | Endpoints |
|---|---|
| Frontend contract (raw JSON, `{error}` failures) | `POST /api/requests`, `GET /api/availability?date=`, `POST /api/request-status`, `GET/POST /api/assistant`, `GET /api/admin/requests`, `PATCH /api/admin/requests/<ref>`, `GET /api/health` |
| Auth (`/api/v1/auth/`) | `register/`, `login/`, `logout/`, `token/refresh/`, `password/reset/`, `password/reset/confirm/`, `verify-email/<key>/`, `resend-verification/`, `social/google/`, `social/google/callback/` |
| User (`/api/v1/users/me/`) | `GET`, `PATCH`, `DELETE` (soft), `avatar/`, `change-password/` |
| Customer dashboard | `GET /api/v1/dashboard/`, `GET /api/v1/requests/mine/`, `GET /api/v1/requests/mine/<ref>/` |
| Public v1 | `POST /api/v1/requests/`, `POST /api/v1/requests/lookup/`, `GET /api/v1/availability/`, `GET/POST /api/v1/assistant/` |
| Team v1 | `GET /api/v1/admin/requests/` (filter, search, order, paginate), `GET/PATCH /api/v1/admin/requests/<ref>/`, `GET /api/v1/admin/stats/` |
| System | `GET /health/`, Swagger `/api/docs/`, ReDoc `/api/redoc/`, schema `/api/schema/` |
| Pages served by Django | `/account/` (login, register, dashboard, profile), `/accounts/reset/<uid>/<token>/` (password reset form), secret `ADMIN_URL` (Unfold admin) |

`/api/v1/*` responses use the envelope `{ success, data, message, errors }`. List endpoints are paginated
(`count, page, total_pages, next, previous, results`).

### Data model
`accounts_users` (custom user, UUID, role `owner|staff|viewer|customer`, soft delete), `leads_request`
(the frontend's `requestKey` is the primary key, so retries are idempotent), `leads_appointment` (partial unique
index on active slots stops double booking), `leads_request_event` (audit ledger with actor),
`leads_assistant_message` (opt-in log). Plus allauth and simplejwt blacklist tables.

### Behaviour worth knowing
- **Consultation slots**: Sun-Thu, Africa/Cairo, 10:00/11:00/12:00/14:00/15:00, tomorrow to +90 days. Canceled/declined requests free their slot.
- **Emails**: visitor confirmation, optional team alert (`TEAM_NOTIFY_EMAIL`), status-change notice, verification, welcome, password reset. Console backend in development, SMTP in production.
- **`/team` console**: paste either `ADMIN_TOKEN` (shared secret, owner rights) or a staff JWT access token (obtained from `POST /api/v1/auth/login/`, valid 15 min). `viewer` is read-only.
- **Assistant**: deterministic catalog guide by default. Set `AI_PROVIDER` (`bedrock`, `compatible`, `dify`) and its variables for a live model; failures fall back to the guide.
- **Accounts**: customers see requests linked to their account plus anonymous requests made with their *verified* email.
- **Throttling**: DB-backed cache so limits are shared by all Gunicorn workers (`createcachetable` is run by the scripts).

## Local development

```powershell
cd backend
uv venv --python 3.12 .venv          # or: python3.12 -m venv .venv
uv pip install --python .venv\Scripts\python.exe -r requirements\test.txt
copy .env.example .env               # optional; development works without it
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createcachetable
.venv\Scripts\python manage.py seed_demo --demo-data   # superuser admin@flowly.local / FlowlyAdmin!2026 (DEBUG only)
.venv\Scripts\python manage.py runserver 3000
```

The frontend's Vite config proxies `/api` to `127.0.0.1:3000`, so running Django on port 3000 lets
`frontend/portable` (`vite dev`) talk to it. Other URLs: admin `http://localhost:3000/admin/`,
account portal `/account/`, Swagger `/api/docs/`.

Development uses SQLite when `DATABASE_URL` is unset; production requires PostgreSQL 16.

### Tests and quality
```powershell
cd backend
.venv\Scripts\python -m pytest -q          # 148 tests (unit + integration)
.venv\Scripts\python -m flake8 apps config tests
.venv\Scripts\python -m black --check --line-length 120 apps config tests

cd ..\frontend
pnpm install --frozen-lockfile
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
node node_modules/vite/bin/vite.js build --config portable/vite.config.ts   # -> ec2-dist/public

cd ..\e2e                                   # real-browser tests against a running site
npm install
$env:BASE_URL="https://yourdomain.com"; $env:ADMIN_TOKEN="<from backend/.env>"; node run.mjs
```
The backend suite covers models, serializers, auth (Google with mocked HTTP), JWT guards (401/403), user APIs,
avatar upload, the full frontend contract (port of `tests/api-integration.mjs`), v1 request/team/dashboard APIs,
Unfold admin pages and actions, error handlers, management commands and the OpenAPI schema.

`e2e/run.mjs` drives Chrome through 16 journeys: every route and internal link, search, language/RTL and theme,
assistant, contact, consultation (slot locking across visitors), the 5-step wizard, status lookup, the `/team`
console (token and staff sign-in, status change, history), the account portal (register, login, profile,
password change), the customer dashboard, mobile layout and security headers. It creates data with
`e2e-*@example.test` addresses; remove it with `manage.py purge_e2e --yes`. It submits 3 requests per run, so
run it at most twice an hour from one IP (public limit: 8 submissions per hour per IP).

The frontend build output `frontend/ec2-dist/public` is committed, so servers need no Node toolchain.
Rebuild it after changing anything under `frontend/components`, `frontend/lib` or `frontend/app`.

## Deploy to AWS EC2

Tested on Ubuntu 26.04 LTS (t3.large); the scripts also target 22.04/24.04. Python 3.12 is installed with
`uv`, independent of the distro's default Python. Requirements: ports 22/80/443 open in the security group,
and for a real domain an Elastic IP with `A` records for `yourdomain.com` (and `www.` if used).

```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/YOU/flowly.git /tmp/flowly && cd /tmp/flowly
sudo REPO_URL=https://github.com/YOU/flowly.git DOMAIN=yourdomain.com LE_EMAIL=you@yourdomain.com \
     bash deploy/ec2-setup.sh       # packages, PostgreSQL, .env with generated secrets, Gunicorn, Nginx, backups
sudo nano /var/www/flowly/backend/.env     # SMTP, TEAM_NOTIFY_EMAIL, Google OAuth, AI provider (optional)
sudo systemctl restart gunicorn
sudo DOMAIN=yourdomain.com LE_EMAIL=you@yourdomain.com bash /var/www/flowly/deploy/ssl-setup.sh
```
`REPO_URL` is optional: without it the script deploys whatever is already in `/var/www/flowly` (for example
an uploaded archive). Without a domain, use `DOMAIN=<ip-with-dashes>.sslip.io` (for example
`13-53-243-42.sslip.io`) to get a working HTTPS hostname, and add `INCLUDE_WWW=0` to `ssl-setup.sh`.

Releases: `sudo bash /var/www/flowly/deploy/deploy.sh` (pull, install, migrate, collectstatic, publish the
frontend, re-render Nginx, restart, health check). Revert: `sudo bash /var/www/flowly/deploy/rollback.sh [commit]`
(code only; migrations are not reversed).

`ec2-setup.sh` generates `SECRET_KEY`, the database password, a secret `ADMIN_URL`, `ADMIN_TOKEN` and the first
superuser password, and writes them to `backend/.env` (mode 600). Read them with
`sudo grep -E '^(ADMIN_URL|DJANGO_SUPERUSER_EMAIL|DJANGO_SUPERUSER_PASSWORD)=' /var/www/flowly/backend/.env`.
Change the superuser password after first login, then delete that line.

### Operations
| What | Where |
|---|---|
| App logs | `sudo journalctl -u gunicorn -f`, `/var/log/flowly/flowly.log` |
| Health | `GET /health/` (DB ping), `GET /api/health` |
| Backups | nightly 02:23 server time: PostgreSQL dump + uploads in `/var/backups/flowly`, 14 days kept. Restore: `sudo -u postgres pg_restore -c -d flowly <file>.dump`. Copy them off the server for disaster recovery. |
| TLS | Let's Encrypt, renewed by cron + certbot timer |
| Emails without SMTP | written to the Gunicorn log instead of being sent; verification is not required until `EMAIL_HOST_USER` is set |

### Capacity
Gunicorn runs 3 workers x 2 threads behind Nginx with PostgreSQL on the same host. That is comfortable for a
marketing and lead-intake site (hundreds of concurrent page views; pages are static files served by Nginx).
It is a single server: no redundancy, and backups live on the same disk until you copy them elsewhere. Move
the database to RDS and add a second instance behind a load balancer if uptime requirements grow.

## Environment variables
Every variable is documented in `backend/.env.example`.

## Not built (outside the MVP, flagged for later)
- File uploads on requests, payments, CMS, analytics, calendar/meeting and CRM connectors.
- S3 (django-storages) and SES: one-setting swaps are ready (`STORAGES`, `EMAIL_BACKEND`).
- Celery/background jobs (emails are sent inline; failures are logged, never break a request), multi-tenant organizations.
- Login and dashboard pages rebuilt inside the React app (the Django-served portal at `/account/` provides them now).
- Argon2 password hashing.