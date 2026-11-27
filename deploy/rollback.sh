#!/usr/bin/env bash
# =============================================================================
# Flowly - one-command rollback.
#
#   sudo bash /var/www/flowly/deploy/rollback.sh            # shows the last 5 commits, restores the previous deploy
#   sudo bash /var/www/flowly/deploy/rollback.sh <commit>   # restores a specific commit
#
# NOTE: this restores code only. Database migrations are NOT reversed. If the bad release added a
# migration, restore a database backup or migrate back manually (manage.py migrate <app> <number>).
# After fixing the problem, run deploy.sh again (it checks out the branch and fast-forwards).
# =============================================================================
set -euo pipefail

APP_USER="${APP_USER:-flowly}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
BACKEND_DIR="${APP_DIR}/backend"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
VENV="${BACKEND_DIR}/.venv"

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
as_app() { sudo -u "$APP_USER" "$@"; }

echo "Recent commits:"
as_app git -C "$APP_DIR" log --oneline -5

TARGET="${1:-}"
if [ -z "$TARGET" ] && [ -f "$APP_DIR/.deploy/previous" ]; then
  TARGET="$(cat "$APP_DIR/.deploy/previous")"
fi
[ -n "$TARGET" ] || { echo "Pass a commit hash: bash rollback.sh <commit>"; exit 1; }
as_app git -C "$APP_DIR" cat-file -e "${TARGET}^{commit}" || { echo "Unknown commit: $TARGET"; exit 1; }

echo "==> git checkout ${TARGET}"
as_app git -C "$APP_DIR" checkout --detach "$TARGET"

echo "==> reinstall dependencies and static files for that commit"
as_app "$VENV/bin/pip" install --quiet -r "$BACKEND_DIR/requirements/production.txt"
as_app bash -c "cd '$BACKEND_DIR' && DJANGO_SETTINGS_MODULE=config.settings.production '$VENV/bin/python' manage.py collectstatic --noinput"
# Rebuild the frontend from the commit we just checked out (the ignored build folder may be from a newer commit).
# Commits from before build-frontend.sh existed have no script: keep the files that are being served.
if [ -f "$APP_DIR/deploy/build-frontend.sh" ]; then
  if APP_USER="$APP_USER" APP_DIR="$APP_DIR" bash "$APP_DIR/deploy/build-frontend.sh"; then
    rm -rf "${FRONTEND_DIR:?}"/*
    cp -a "$APP_DIR/frontend/ec2-dist/public/." "$FRONTEND_DIR/"
    chmod -R a+rX "$FRONTEND_DIR"
  else
    echo "WARNING: frontend rebuild failed. The frontend files currently served were NOT changed."
  fi
else
  echo "NOTE: this commit has no build-frontend.sh. The frontend files currently served were NOT changed."
fi
chmod -R a+rX "$BACKEND_DIR/staticfiles"

echo "==> systemctl restart gunicorn"
systemctl restart gunicorn
nginx -t && systemctl reload nginx

for i in $(seq 1 20); do
  if curl -fsS -H "X-Forwarded-Proto: https" http://127.0.0.1:8000/health/ >/dev/null 2>&1; then
    echo "Rolled back to $(as_app git -C "$APP_DIR" log --oneline -1). Healthy."
    exit 0
  fi
  sleep 2
done
echo "Health check failed after rollback: journalctl -u gunicorn -n 80 --no-pager"
exit 1
