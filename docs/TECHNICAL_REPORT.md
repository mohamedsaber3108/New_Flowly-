# Flowly: technical report

Status as of commit `13cd78e` on `main` (github.com/mohamedsaber3108/New_Flowly-), deployed to
`https://flowly.usamif.com` on AWS EC2 (eu-north-1, t3.large, Ubuntu 26.04, server IP 13.53.243.42).

Each claim below is tagged:
- **Verified**: executed and observed (tests, browser runs, production checks).
- **Built, needs configuration**: code is complete but depends on credentials you provide.
- **Not built**: outside this product's scope.

---

## 1. Architecture

```
Browser ──HTTPS──► nginx (TLS, security headers, rate limits, static files)
                     ├── /                → React site (frontend/ec2-dist/public, static files)
                     ├── /assets /fonts   → hashed static files, cached 1 year
                     ├── /static /media   → Django collectstatic output, uploaded avatars
                     └── /api /health /account /accounts /<ADMIN_URL> /robots.txt /sitemap.xml
                              │
                              ▼
                     Gunicorn (3 workers × 2 threads) ─► Django 5.2 + DRF ─► PostgreSQL (same host)
                                                              └─► SMTP, Google OAuth, AI provider (optional)
```

| Part | Technology | Location |
|---|---|---|
| Public website | React 19 + Vite, bilingual EN/AR, RTL, light/dark | `frontend/` (built to `frontend/ec2-dist/public`) |
| API + admin + account portal | Django 5.2, DRF 3.16, simplejwt, allauth, Unfold | `backend/` |
| Database | PostgreSQL (production), SQLite (local development) | Django migrations |
| Deployment | Bash scripts, systemd, nginx, Let's Encrypt, cron | `deploy/` |
| Browser and load tests | playwright-core, Node fetch | `e2e/` |

The product is a services website with lead intake, consultation booking, request tracking, a team
console, customer accounts and an admin back office. It sells scoped engagements, so it has no
course catalogue, checkout, subscriptions or coupons (see section 9).

## 2. Frontend

**Verified** in Chrome on the live site by `e2e/run.mjs`, 16/16 journeys:

| Area | Pages / features |
|---|---|
| Marketing | Home, 45 service pages, 14 industry pages, government, about, approach, engagement, pricing, 3 insight articles, procurement, support |
| Policy | Privacy, terms, security, accessibility, responsible AI |
| Intake | Contact form, consultation booking (live slot availability, a booked slot is disabled for other visitors), 5-step discovery wizard with recommendations |
| Tracking | `/status`: reference + email lookup; wrong email rejected; private notes never shown |
| Assistant | Catalog-grounded guide in EN/AR; uses a live AI model when configured |
| Team console `/team` | Staff email/password sign-in or admin token, search, filter, status change, private note, CSV export, request history |
| Account portal `/account/` | Register, sign in, forgot password, dashboard, my requests, request timeline, profile, avatar, change password, delete account |
| Cross-cutting | Every internal link resolves; Arabic RTL and dark mode persist; mobile menu; no horizontal scroll at 390px; no console errors |

Changes in this release:
- **Team console:** staff sign-in with token refresh, request history panel, read-only handling for viewers.
- **Footer:** links to the account portal.
- **Success receipt:** now states that a receipt email is sent (it previously said none was).
- **Account portal:** redesigned with the Flowly brand. It shares the site's language and theme settings, so Arabic visitors get an Arabic, right-to-left portal. The Google button appears only when Google sign-in is configured.
- **Fixed:** the hidden skip link pushed Arabic pages 9,999px wide and blocked clicks on mobile.
- **Fixed:** the word "null" rendered on the dashboard.
- **Local development:** the Vite dev server now proxies every Django path, so `http://127.0.0.1:5173` behaves like production.

## 3. Backend and APIs

Interactive documentation: `/api/docs/` (Swagger) and `/api/redoc/`.

| Group | Endpoints |
|---|---|
| Original frontend contract (raw JSON) | `POST /api/requests`, `GET /api/availability`, `POST /api/request-status`, `GET/POST /api/assistant`, `GET /api/admin/requests`, `PATCH /api/admin/requests/<ref>`, `GET /api/health` |
| Auth | `/api/v1/auth/` register, login, logout, token/refresh, password/reset, password/reset/confirm, verify-email/<key>, resend-verification, social/google, social/google/callback |
| Current user | `/api/v1/users/me/` GET/PATCH/DELETE (soft delete), `me/avatar/`, `me/change-password/` |
| Customer | `/api/v1/dashboard/`, `/api/v1/requests/mine/`, `/api/v1/requests/mine/<ref>/` |
| Public v1 | `/api/v1/requests/`, `/api/v1/requests/lookup/`, `/api/v1/availability/`, `/api/v1/assistant/` |
| Team v1 | `/api/v1/admin/requests/` (filter, search, order, paginate), `/api/v1/admin/requests/<ref>/`, `/api/v1/admin/stats/` |
| System | `/health/`, `/robots.txt`, `/sitemap.xml`, `/api/schema/` |

**Roles:**
- **owner, staff:** read and change requests.
- **viewer:** read-only team access.
- **customer:** sees only their own requests, plus anonymous requests made with their *verified* email.

The shared `ADMIN_TOKEN` acts as owner for the original `/team` console.

**Emails:** visitor receipt, team alert (`TEAM_NOTIFY_EMAIL`), status change, verification, welcome and password reset.
Built, needs configuration: SMTP credentials. Until they are set, emails are written to the application log and login does
not require email verification. Without a mail server nobody could verify, so sign-up would be unusable.

### Admin (Django admin at the secret `ADMIN_URL`)

**Verified** by admin tests and a screenshot review:
- **Dashboard** on live data:
  - totals, last 30 days, pending review, open pipeline, upcoming consultations and customer accounts
  - an 8-week chart
  - breakdowns by status, type and audience, each linking to a filtered list
  - next consultations and latest requests
- **Requests:** search, filters, appointment and history inlines, CSV export (protected against spreadsheet formula injection), bulk status actions.
- **Other models:** appointments, request events, assistant log, users (roles, status, soft delete), email addresses.
- **Fixed this release:** editing a request's status, note or assignee in the admin now goes through the same logic as the console and API. Before, a declined request kept its slot blocked, the customer was not emailed, and re-confirming a slot that someone else had taken crashed with a server error.
- **Assignees:** limited to active team members.
- **Branding:** the admin uses Flowly colours and favicon.

## 4. Database

Tables:
- `accounts_users`: custom user with UUID, role, status and soft delete.
- `leads_request`: the browser's `requestKey` is the primary key, which makes retries idempotent.
- `leads_appointment`: a partial unique index on active slots prevents double booking.
- `leads_request_event`: audit trail with the acting user.
- `leads_assistant_message`: assistant log, opt-in.

allauth, simplejwt-blacklist and Django tables sit alongside these.

**Verified:**
- **Migrations:** apply cleanly on PostgreSQL in production, and `makemigrations --check` reports no drift.
- **Foreign keys:** every one declares `on_delete`. Users are only soft-deleted, and requests keep their history.
- **Backups:** a nightly `pg_dump` plus uploads archive runs at 02:23 server time and keeps 14 days in `/var/backups/flowly`. A manual backup run succeeded.
- **Restore** (written, not run): `sudo -u postgres pg_restore -c -d flowly <file>.dump`.

## 5. Security

**Verified on production:**
- TLS from Let's Encrypt, valid until 8 Feb 2027, renewed by cron. HTTP redirects to HTTPS.
- **One consistent set of headers on every response**, which previously came duplicated and conflicting from nginx and Django:
  - HSTS, `nosniff`, `X-Frame-Options`, `Referrer-Policy`
  - `Permissions-Policy`
  - a strict Content-Security-Policy on the site (scripts, styles, fonts and API calls from the site's own origin only)
  - a sandbox policy on uploaded media
- **Unknown hostnames dropped:** requests addressed to the bare IP (scanners) are closed by nginx before they reach Django. Before this, bots produced the application's only error-log entries.
- **Secrets:** the secret admin path, `SECRET_KEY`, the DB password and `ADMIN_TOKEN` are generated on the server and stored in `backend/.env` (mode 600). No secret is in the repository (checked on every commit).
- **Rate limits:** nginx limits 20 req/s on the API and 5 req/s on auth per IP. Django limits 8 submissions/hour, 20 status lookups/hour and 30 assistant messages/hour per IP, plus login, register and reset limits.
- **Validation and output:** every input is validated by a serializer and the ORM is used throughout. Customer views never include internal notes. Unhandled errors return a clean 500 with no stack trace.
- **Production settings:** `DEBUG` is forced off, and the app refuses to start without a real `SECRET_KEY`, explicit `ALLOWED_HOSTS` and PostgreSQL.

## 6. Performance and reliability

**Verified load test** (`e2e/load.mjs`, 50 concurrent clients from one remote machine): about 390–440 requests/s, p50 85–93 ms, p95 170–290 ms,
memory steady at about 0.8 of 7.8 GB, zero 5xx responses in the server logs.

**Fixed this release:** nginx reused open connections to Gunicorn, so the request in flight on a reused connection was dropped
whenever Gunicorn restarted a worker (about 1 in 3,000 requests). Reuse is now off, and Gunicorn spreads worker restarts out
(`max_requests_jitter`). Across the remaining test runs the server logged no failed responses. One request per run was still lost
on the network between the test machine and the server, and it never reached nginx as an error.

Caching: hashed assets and fonts are cached for a year, the HTML shell revalidates on every load (new deploys appear
immediately), API responses are not cached, and gzip is on. The API itself was not load-tested from one machine,
because the per-IP rate limits block that by design.

Monitoring: `sudo bash /var/www/flowly/deploy/status-report.sh` prints services, response codes, recent 5xx responses,
upstream errors, application errors, resources, the latest backups and certificate expiry. Logs are in `journalctl -u gunicorn` and
`/var/log/flowly/flowly.log`.

**Limits:** this is a single server. There is no failover, and backups live on the same disk until you copy them elsewhere (for example to S3).
For higher availability, move the database to RDS and run two instances behind a load balancer.

## 7. Testing

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration | `cd backend; .venv\Scripts\python -m pytest -q` | **153 passed** |
| Lint / format | `flake8 apps config tests` · `black --check` · `isort --check` | clean |
| Migrations drift | `manage.py makemigrations --check --dry-run` | no changes |
| Frontend types + build | `tsc --noEmit` · `vite build --config portable/vite.config.ts` | pass |
| Browser journeys (live HTTPS) | `cd e2e; node run.mjs` | **16/16 passed**, no console errors |
| Visual (EN/AR, light/dark, desktop/mobile) | `node visual.mjs` | no overflow, no failed requests, screenshots reviewed |
| Load | `node load.mjs` | figures in section 6 |
| Production headers | `bash deploy/check-headers.sh https://<host>` | single, correct values |

Browser tests ran in Chrome only. Cross-browser testing (Safari, Firefox) was not run.
Test data uses `e2e-*@example.test` addresses and is removed with `manage.py purge_e2e --yes`, which was run after each production test run.

## 8. Bugs fixed during this audit

| Bug | Effect | Fix |
|---|---|---|
| Arabic portal page widened by the hidden skip link | 9,999px horizontal scroll; clicks blocked on mobile | Direction-independent hiding |
| `null` rendered on the portal dashboard | Stray text for verified users | Empty nodes filtered before rendering |
| Admin status edits skipped the shared status logic | Slots stayed blocked, no customer email, crash on slot conflict | Admin edits use `services.update_request` |
| nginx reused connections to Gunicorn | About 1 in 3,000 requests dropped when a worker restarted | Connection reuse removed |
| Duplicate and conflicting security headers | Two HSTS and two `X-Frame-Options` values on API pages | nginx is the single source; adds CSP and Permissions-Policy |
| Bot traffic reaching Django | Error-log noise, wasted work | Unknown-host catch-all closes those connections in nginx |
| Footer "My account" opened the React 404 page in local development | Broken link on `localhost:5173` | Vite proxies all Django paths |
| Account portal in English only, off-brand | Inconsistent product in Arabic | Branded, bilingual, RTL, dark mode |
| Generic purple admin theme with little reporting | Not usable as a back office | Flowly brand, live dashboard |
| Redeploying the same commit overwrote the rollback target | `rollback.sh` would restore the current version | Target only moves when a deploy brings a new commit |

## 9. Remaining items

**Built, needs your configuration** (all in `/var/www/flowly/backend/.env`, then `sudo systemctl restart gunicorn`):

1. **SMTP:** `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `TEAM_NOTIFY_EMAIL`. Without SMTP, customers get no receipts or status emails.
2. **Google sign-in:** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`. The redirect URI is `https://<domain>/api/v1/auth/social/google/callback/`. Tested only against mocked Google responses.
3. **AI assistant:** `AI_PROVIDER` plus that provider's keys. Without them the assistant uses the service catalogue. Tested only with a mocked provider.

**External actions:**

4. **Elastic IP:** attach one to the instance, otherwise the address changes when it stops.
5. **Domain:** done. The `flowly.usamif.com` A record points at 13.53.243.42. If you attach an Elastic IP, update that record to the new IP.
6. **Off-server backups:** copy `/var/backups/flowly` to S3 or similar.

**Not built**, because this product sells scoped engagements and none of these are part of it:
- courses, product catalogue, checkout, payments, subscriptions, invoices, coupons and campaigns
- a CMS (services and articles live in `frontend/lib/catalog.ts`)
- third-party analytics, file uploads on requests, calendar and CRM connectors
- background job queue (emails are sent inline, and failures are logged without breaking the request)

Add these only if the business model changes. The data model and admin are structured so new apps can be added alongside `leads`.

## 10. Deployment

First install on a new server: see `README.md`, "Deploy to AWS EC2".

Routine release:
```powershell
# your PC
cd M:\New_Flowly
git add -A; git commit -m "describe the change"; git push
```
```bash
# the server
sudo bash /var/www/flowly/deploy/deploy.sh      # ends with "Deploy OK (<commit>)"
sudo bash /var/www/flowly/deploy/rollback.sh    # restores the previous release (code only)
sudo bash /var/www/flowly/deploy/status-report.sh
```

Switching from the temporary hostname to your domain (after the DNS `A` record points at the Elastic IP):
```bash
sudo sed -i 's/13-53-243-42.sslip.io/yourdomain.com/g' /var/www/flowly/backend/.env
sudo DOMAIN=yourdomain.com LE_EMAIL=you@yourdomain.com bash /var/www/flowly/deploy/ssl-setup.sh
sudo DOMAIN=yourdomain.com bash /var/www/flowly/deploy/deploy.sh
```
Add `INCLUDE_WWW=0` before `bash` in the `ssl-setup.sh` line if `www` has no DNS record. If the IP changes when you attach the
Elastic IP, replace `13-53-243-42` in the first command with the old address written with dashes.

Every environment variable is documented in `backend/.env.example`.
