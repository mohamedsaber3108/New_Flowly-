#!/usr/bin/env bash
# =============================================================================
# Flowly - one-command deploy. Run on the server as root (or via sudo):
#
#   sudo bash /var/www/flowly/deploy/deploy.sh
#
# Optional: BRANCH (default main), APP_USER, APP_DIR, FRONTEND_DIR.
# Records the previous commit in .deploy/previous so rollback.sh can restore it.
# =============================================================================
set -euo pipefail

BRANCH="${BRANCH:-main}"
APP_USER="${APP_USER:-flowly}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
VENV="${BACKEND_DIR}/.venv"

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
as_app() { sudo -u "$APP_USER" "$@"; }
manage() { as_app bash -c "cd '$BACKEND_DIR' && DJANGO_SETTINGS_MODULE=config.settings.production '$VENV/bin/python' manage.py $*"; }

mkdir -p "$APP_DIR/.deploy"
chown "$APP_USER":"$APP_USER" "$APP_DIR/.deploy"
if [ -d "$APP_DIR/.git" ]; then
  PREVIOUS="$(as_app git -C "$APP_DIR" rev-parse HEAD)"
  echo "$PREVIOUS" > "$APP_DIR/.deploy/previous"
  echo "==> git pull origin ${BRANCH}"
  as_app git -C "$APP_DIR" fetch origin "$BRANCH"
  as_app git -C "$APP_DIR" checkout "$BRANCH"   # leaves a detached HEAD left by rollback.sh
  as_app git -C "$APP_DIR" pull --ff-only origin "$BRANCH"
  echo "Deploying $(as_app git -C "$APP_DIR" log --oneline -1)"
else
  PREVIOUS="uploaded-tree"
  echo "No git repository in ${APP_DIR}: deploying the files already on disk (uploaded copy)."
fi
echo "==> pip install -r requirements/production.txt"
as_app "$VENV/bin/pip" install --quiet -r "$BACKEND_DIR/requirements/production.txt"

echo "==> migrate / cache table / collectstatic"
manage migrate --noinput
manage createcachetable
manage collectstatic --noinput

if [ -d "$APP_DIR/frontend/ec2-dist/public" ]; then
  echo "==> publish React build -> ${FRONTEND_DIR}"
  mkdir -p "$FRONTEND_DIR"
  rm -rf "${FRONTEND_DIR:?}"/*
  cp -a "$APP_DIR/frontend/ec2-dist/public/." "$FRONTEND_DIR/"
  chmod -R a+rX "$FRONTEND_DIR"
fi
chmod -R a+rX "$BACKEND_DIR/staticfiles"

echo "==> ensure nightly backup cron"
chmod +x "$APP_DIR"/deploy/*.sh
echo "23 2 * * * root MEDIA_DIR=${MEDIA_DIR:-/var/www/flowly-media} $APP_DIR/deploy/backup.sh >> /var/log/flowly/backup.log 2>&1" > /etc/cron.d/flowly-backup
chmod 644 /etc/cron.d/flowly-backup

echo "==> refresh systemd unit, restart gunicorn"
sed "s#__APP_USER__#${APP_USER}#g; s#__BACKEND_DIR__#${BACKEND_DIR}#g" "$APP_DIR/deploy/gunicorn.service" \
  > /etc/systemd/system/gunicorn.service
systemctl daemon-reload
systemctl restart gunicorn

echo "==> render nginx config, reload"
DOMAIN="${DOMAIN:-$(grep -E '^FRONTEND_URL=' "$BACKEND_DIR/.env" | head -n1 | sed 's#.*://##; s#/.*##')}" APP_DIR="$APP_DIR" FRONTEND_DIR="$FRONTEND_DIR" bash "$APP_DIR/deploy/render-nginx.sh"

echo "==> health check"
for i in $(seq 1 20); do
  if curl -fsS -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/health/ >/dev/null 2>&1; then
    echo "Deploy OK. Previous: ${PREVIOUS:0:7} (rollback needs a git checkout: bash deploy/rollback.sh)"
    exit 0
  fi
  sleep 2
done
echo "Health check FAILED. Logs: journalctl -u gunicorn -n 80 --no-pager"
echo "Rollback with: sudo bash ${APP_DIR}/deploy/rollback.sh ${PREVIOUS:0:7}"
exit 1
