#!/usr/bin/env bash
# Render deploy/nginx.conf into /etc/nginx/sites-available/flowly and reload nginx.
# Usage: DOMAIN=yourdomain.com bash render-nginx.sh   (run as root; called by ec2-setup.sh and deploy.sh)
# If the new configuration fails `nginx -t`, the previous one is restored and nginx keeps serving.
set -euo pipefail
: "${DOMAIN:?Set DOMAIN}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
BACKEND_DIR="${APP_DIR}/backend"
MEDIA_DIR="${MEDIA_DIR:-/var/www/flowly-media}"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
SITE=/etc/nginx/sites-available/flowly
HEADERS=/etc/nginx/snippets/flowly-security-headers.conf

ADMIN_URL="$(grep -E '^ADMIN_URL=' "${BACKEND_DIR}/.env" | head -n1 | cut -d= -f2- | sed 's#^/*##; s#/*$##')"
ADMIN_URL="${ADMIN_URL:-admin}/"

mkdir -p /etc/nginx/snippets
[ -f "$SITE" ] && cp "$SITE" "$SITE.bak"
[ -f "$HEADERS" ] && cp "$HEADERS" "$HEADERS.bak"

cp "${APP_DIR}/deploy/nginx-security-headers.conf" "$HEADERS"
sed "s#__DOMAIN__#${DOMAIN}#g; s#__BACKEND_DIR__#${BACKEND_DIR}#g; s#__MEDIA_DIR__#${MEDIA_DIR}#g; s#__FRONTEND_DIR__#${FRONTEND_DIR}#g; s#__ADMIN_URL__#${ADMIN_URL}#g" \
  "${APP_DIR}/deploy/nginx.conf" > "$SITE"
ln -sf "$SITE" /etc/nginx/sites-enabled/flowly
rm -f /etc/nginx/sites-enabled/default

if ! nginx -t; then
  echo "New nginx configuration is invalid; restoring the previous one." >&2
  [ -f "$SITE.bak" ] && mv "$SITE.bak" "$SITE"
  [ -f "$HEADERS.bak" ] && mv "$HEADERS.bak" "$HEADERS"
  nginx -t
  exit 1
fi
rm -f "$SITE.bak" "$HEADERS.bak"
systemctl reload nginx || systemctl restart nginx
