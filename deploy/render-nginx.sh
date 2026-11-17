#!/usr/bin/env bash
# Render deploy/nginx.conf into /etc/nginx/sites-available/flowly and reload nginx.
# Usage: DOMAIN=yourdomain.com bash render-nginx.sh   (run as root; called by ec2-setup.sh and deploy.sh)
set -euo pipefail
: "${DOMAIN:?Set DOMAIN}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
BACKEND_DIR="${APP_DIR}/backend"
MEDIA_DIR="${MEDIA_DIR:-/var/www/flowly-media}"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
ADMIN_URL="$(grep -E '^ADMIN_URL=' "${BACKEND_DIR}/.env" | head -n1 | cut -d= -f2- | sed 's#^/*##; s#/*$##')"
ADMIN_URL="${ADMIN_URL:-admin}/"
sed "s#__DOMAIN__#${DOMAIN}#g; s#__BACKEND_DIR__#${BACKEND_DIR}#g; s#__MEDIA_DIR__#${MEDIA_DIR}#g; s#__FRONTEND_DIR__#${FRONTEND_DIR}#g; s#__ADMIN_URL__#${ADMIN_URL}#g" \
  "${APP_DIR}/deploy/nginx.conf" > /etc/nginx/sites-available/flowly
ln -sf /etc/nginx/sites-available/flowly /etc/nginx/sites-enabled/flowly
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx || systemctl restart nginx