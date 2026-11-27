#!/usr/bin/env bash
# =============================================================================
# Flowly - publish the built frontend into the folder nginx serves, without a gap.
#
#   sudo bash /var/www/flowly/deploy/publish-frontend.sh
#
# Copies ${APP_DIR}/frontend/ec2-dist/public into "${FRONTEND_DIR}.new", then swaps it in:
# the old folder is renamed to "${FRONTEND_DIR}.old", the new one is renamed into place, and .old is removed.
# The served folder is never emptied before the new files exist. Exits non-zero (and changes nothing)
# if the build folder has no index.html. Optional: APP_DIR, FRONTEND_DIR.
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/flowly}"
FRONTEND_DIR="${FRONTEND_DIR:-/var/www/frontend}"
SRC="${APP_DIR}/frontend/ec2-dist/public"
NEW="${FRONTEND_DIR}.new"
OLD="${FRONTEND_DIR}.old"

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
[ -s "$SRC/index.html" ] || {
  echo "FRONTEND BUILD MISSING: ${SRC}/index.html. The served frontend was not changed." >&2
  exit 1
}

# A crash between the two renames below leaves no served folder: put the old one back first.
if [ ! -e "$FRONTEND_DIR" ] && [ -d "$OLD" ]; then mv "$OLD" "$FRONTEND_DIR"; fi

rm -rf "${NEW:?}" "${OLD:?}"
mkdir -p "$NEW"
cp -a "$SRC/." "$NEW/"
chmod -R a+rX "$NEW"

if [ -e "$FRONTEND_DIR" ]; then mv "$FRONTEND_DIR" "$OLD"; fi
if ! mv "$NEW" "$FRONTEND_DIR"; then
  [ -d "$OLD" ] && mv "$OLD" "$FRONTEND_DIR"
  echo "Could not move the new frontend into place; the old files were restored." >&2
  exit 1
fi
rm -rf "${OLD:?}"
echo "Published frontend -> ${FRONTEND_DIR}"
