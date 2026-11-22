#!/usr/bin/env bash
# Print the security and cache headers for each kind of response the site serves.
# Usage: bash deploy/check-headers.sh https://yourdomain.com
set -euo pipefail
BASE="${1:?Usage: check-headers.sh https://yourdomain.com}"
ASSET="$(curl -fsS "$BASE/" | grep -oE '/assets/index-[A-Za-z0-9_-]+\.js' | head -n1)"
for path in / "$ASSET" /fonts/manrope-400.ttf /api/health /health/ /account/ /static/account/portal.js; do
  echo "== $path"
  curl -sSI "$BASE$path" | tr -d '\r' \
    | grep -iE '^(HTTP/|strict-transport-security|x-frame-options|x-content-type-options|referrer-policy|content-security-policy|permissions-policy|cache-control):' \
    | sort
done
