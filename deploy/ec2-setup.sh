#!/usr/bin/env bash
# =============================================================================
# Flowly - full server bootstrap for Ubuntu 22.04 LTS (t2.micro or larger).
# Idempotent: safe to re-run. Run as root:
#
#   sudo REPO_URL=https://github.com/you/flowly.git DOMAIN=yourdomain.com \
#        LE_EMAIL=you@yourdomain.com bash deploy/ec2-setup.sh
#
# Optional: BRANCH (default main), APP_USER (default flowly), DB_NAME/DB_USER (default flowly),
#           SWAP_MB (default 1024; t2.micro has 1 GB RAM).
# =============================================================================
set -euo pipefail

REPO_URL="${REPO_URL:-}"   # optional: if empty, the project must already be uploaded to ${APP_DIR}
: "${DOMAIN:?Set DOMAIN, e.g. yourdomain.com}"
LE_EMAIL="${LE_EMAIL:-admin@${DOMAIN}}"
BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-flowly}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
MEDIA_DIR="${MEDIA_DIR:-/var/www/flowly-media}"
LOG_DIR="${LOG_DIR:-/var/log/flowly}"
DB_NAME="${DB_NAME:-flowly}"
DB_USER="${DB_USER:-flowly}"
SWAP_MB="${SWAP_MB:-1024}"
ENV_FILE="${BACKEND_DIR}/.env"

log() { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

log "System packages"
apt-get update -y
apt-get upgrade -y
apt-get install -y software-properties-common ca-certificates curl git ufw nginx postgresql postgresql-contrib \
  libpq-dev build-essential openssl cron
# Python 3.12 via uv (standalone build): independent of the Ubuntu release and its default Python.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
export UV_PYTHON_INSTALL_DIR=/opt/uv-python
uv python install 3.12
chmod -R a+rX /opt/uv-python
apt-get install -y certbot python3-certbot-nginx rsync
log "Swap (t2.micro safety)"
if [ "$SWAP_MB" -gt 0 ] && ! swapon --show | grep -q '/swapfile'; then
  fallocate -l "${SWAP_MB}M" /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "Firewall (UFW: 22, 80, 443)"
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

log "Application user and directories"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
mkdir -p "$APP_DIR" "$MEDIA_DIR" "$LOG_DIR" "$FRONTEND_DIR" /var/www/certbot
chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "$LOG_DIR" "$MEDIA_DIR"
chmod 755 "$APP_DIR" "$MEDIA_DIR" "$FRONTEND_DIR"

log "Repository"
if [ -d "$APP_DIR/.git" ] && [ -n "$REPO_URL" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" fetch --all --prune
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
elif [ -n "$REPO_URL" ] && [ ! -f "$BACKEND_DIR/manage.py" ]; then
  sudo -u "$APP_USER" git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
  echo "Using the code already present in ${APP_DIR}"
fi
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
[ -f "$BACKEND_DIR/manage.py" ] || { echo "backend/manage.py not found in the repository root."; exit 1; }

log "PostgreSQL database"
systemctl enable --now postgresql
DB_PASS_FILE="/root/.flowly_db_password"
if [ ! -f "$DB_PASS_FILE" ]; then
  openssl rand -hex 24 > "$DB_PASS_FILE"
  chmod 600 "$DB_PASS_FILE"
fi
DB_PASS="$(cat "$DB_PASS_FILE")"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}'"
else
  sudo -u postgres psql -c "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASS}'"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "$DB_USER" "$DB_NAME"
fi

log "Environment file (${ENV_FILE})"
set_env() { # set_env KEY VALUE  (only if KEY is missing, so edits are preserved)
  if ! grep -qE "^$1=" "$ENV_FILE"; then printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"; fi
}
FIRST_ENV=0
if [ ! -f "$ENV_FILE" ]; then
  FIRST_ENV=1
  cp "$BACKEND_DIR/.env.example" "$ENV_FILE"
  # Drop the placeholder lines for keys we generate below.
  sed -i -E '/^(SECRET_KEY|DATABASE_URL|ALLOWED_HOSTS|ADMIN_URL|FRONTEND_URL|SITE_URL|PUBLIC_ORIGIN|CORS_ALLOWED_ORIGINS|CSRF_TRUSTED_ORIGINS|MEDIA_ROOT|LOG_DIR|ADMIN_TOKEN|DJANGO_SUPERUSER_EMAIL|DJANGO_SUPERUSER_PASSWORD|DEFAULT_FROM_EMAIL|SECURE_SSL_REDIRECT)=/d' "$ENV_FILE"
fi
set_env SECRET_KEY "$(openssl rand -base64 60 | tr -d '\n=+/' | cut -c1-64)"
set_env DATABASE_URL "postgres://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}"
set_env ALLOWED_HOSTS "${DOMAIN},www.${DOMAIN}"
set_env ADMIN_URL "manage-$(openssl rand -hex 6)/"
set_env FRONTEND_URL "https://${DOMAIN}"
set_env SITE_URL "https://${DOMAIN}"
set_env PUBLIC_ORIGIN "https://${DOMAIN}"
set_env CORS_ALLOWED_ORIGINS "https://${DOMAIN}"
set_env CSRF_TRUSTED_ORIGINS "https://${DOMAIN}"
set_env MEDIA_ROOT "$MEDIA_DIR"
set_env LOG_DIR "$LOG_DIR"
set_env ADMIN_TOKEN "$(openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-48)"
set_env DEFAULT_FROM_EMAIL "Flowly <noreply@${DOMAIN}>"
set_env DJANGO_SUPERUSER_EMAIL "$LE_EMAIL"
set_env SECURE_SSL_REDIRECT "True"
if [ "$FIRST_ENV" -eq 1 ]; then
  SUPERUSER_PASSWORD="$(openssl rand -base64 18 | tr -d '\n=+/')A1!"
  set_env DJANGO_SUPERUSER_PASSWORD "$SUPERUSER_PASSWORD"
fi
chown "$APP_USER":"$APP_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

log "Python virtualenv and dependencies"
sudo -u "$APP_USER" env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv venv --seed --python 3.12 --allow-existing "$BACKEND_DIR/.venv"
sudo -u "$APP_USER" "$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip wheel
sudo -u "$APP_USER" "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements/production.txt"

run_manage() { # python-decouple reads backend/.env itself, so the file is never sourced by a shell
  sudo -u "$APP_USER" bash -c "cd '$BACKEND_DIR' && DJANGO_SETTINGS_MODULE=config.settings.production '$BACKEND_DIR/.venv/bin/python' manage.py $*"
}

log "Database migrations, cache table, static files, first superuser"
# SECURE_SSL_REDIRECT does not affect management commands.
run_manage migrate --noinput
run_manage createcachetable
run_manage collectstatic --noinput
run_manage seed_demo

log "React frontend build -> ${FRONTEND_DIR}"
APP_USER="$APP_USER" APP_DIR="$APP_DIR" bash "$APP_DIR/deploy/build-frontend.sh"  # installs Node 22 if missing; stops on failure
rsync -a --delete "$APP_DIR/frontend/ec2-dist/public/" "$FRONTEND_DIR/" 2>/dev/null \
  || { rm -rf "${FRONTEND_DIR:?}"/*; cp -a "$APP_DIR/frontend/ec2-dist/public/." "$FRONTEND_DIR/"; }
chmod -R a+rX "$FRONTEND_DIR" "$MEDIA_DIR" "$BACKEND_DIR/staticfiles"

log "Gunicorn systemd service"
sed "s#__APP_USER__#${APP_USER}#g; s#__BACKEND_DIR__#${BACKEND_DIR}#g" "$APP_DIR/deploy/gunicorn.service" \
  > /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl enable gunicorn
systemctl restart gunicorn

log "Nginx"
# Until Let's Encrypt issues a real certificate, serve HTTPS with a temporary self-signed one.
mkdir -p /etc/nginx/snippets /etc/ssl/flowly-temp
if [ ! -f /etc/nginx/snippets/flowly-ssl.conf ]; then
  if [ ! -f /etc/ssl/flowly-temp/privkey.pem ]; then
    openssl req -x509 -nodes -newkey rsa:2048 -days 30 -subj "/CN=${DOMAIN}" \
      -keyout /etc/ssl/flowly-temp/privkey.pem -out /etc/ssl/flowly-temp/fullchain.pem
  fi
  cat > /etc/nginx/snippets/flowly-ssl.conf <<EOF
ssl_certificate     /etc/ssl/flowly-temp/fullchain.pem;
ssl_certificate_key /etc/ssl/flowly-temp/privkey.pem;
EOF
fi
DOMAIN="$DOMAIN" APP_DIR="$APP_DIR" MEDIA_DIR="$MEDIA_DIR" FRONTEND_DIR="$FRONTEND_DIR" bash "$APP_DIR/deploy/render-nginx.sh"
systemctl enable nginx
systemctl reload nginx || systemctl restart nginx

log "Nightly backups (cron)"
chmod +x "$APP_DIR"/deploy/*.sh
echo "23 2 * * * root DB_NAME=$DB_NAME MEDIA_DIR=$MEDIA_DIR $APP_DIR/deploy/backup.sh >> /var/log/flowly/backup.log 2>&1" > /etc/cron.d/flowly-backup
chmod 644 /etc/cron.d/flowly-backup

log "Health check"
for i in $(seq 1 15); do
  if curl -fsS -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/health/ >/dev/null 2>&1; then echo "Gunicorn healthy."; break; fi
  sleep 2
  [ "$i" -eq 15 ] && { echo "Gunicorn did not become healthy: journalctl -u gunicorn -n 50"; exit 1; }
done

cat <<EOF

Setup complete.
  Site (temporary certificate until SSL step): https://${DOMAIN}/
  Admin path:   https://${DOMAIN}/$(grep '^ADMIN_URL=' "$ENV_FILE" | cut -d= -f2)
  Env file:     ${ENV_FILE}   (add SMTP, Google OAuth, TEAM_NOTIFY_EMAIL, AI settings, then: systemctl restart gunicorn)
  Superuser:    $(grep '^DJANGO_SUPERUSER_EMAIL=' "$ENV_FILE" | cut -d= -f2)  (password: DJANGO_SUPERUSER_PASSWORD in the env file; change it after first login, then remove it)

Next:  sudo DOMAIN=${DOMAIN} LE_EMAIL=${LE_EMAIL} bash ${APP_DIR}/deploy/ssl-setup.sh
EOF
