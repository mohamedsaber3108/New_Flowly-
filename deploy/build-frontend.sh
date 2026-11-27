#!/usr/bin/env bash
# =============================================================================
# Flowly - build the React frontend from the checked-out commit.
#
#   sudo bash /var/www/flowly/deploy/build-frontend.sh
#
# Output: ${APP_DIR}/frontend/ec2-dist/public (git-ignored, never committed).
# Idempotent: checks free memory first (MemAvailable >= 2048 MB, else exits before changing anything),
# installs Node 22 only when missing or older (NodeSource apt repository, signed key owned by NodeSource),
# installs dependencies with the lockfile (--frozen-lockfile, pnpm pinned by packageManager through Corepack),
# then runs the same vite build that CI runs on every pull request, with the Node heap capped at 1536 MB.
# Exits non-zero with a clear message when the build fails or index.html is missing, so deploy.sh
# stops before it touches the live frontend files.
# Writes one line (time, commit, sha256 of index.html) to ${APP_DIR}/.deploy/deploy.log.
# Optional: APP_USER, APP_DIR.
# =============================================================================
set -euo pipefail

APP_USER="${APP_USER:-flowly}"
APP_DIR="${APP_DIR:-/var/www/flowly}"
FRONTEND_SRC="${APP_DIR}/frontend"
OUT_DIR="${FRONTEND_SRC}/ec2-dist/public"
NODE_MAJOR=22

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
fail() { echo "FRONTEND BUILD FAILED: $*" >&2; exit 1; }
# NODE_OPTIONS caps Node's heap at 1536 MB so a build cannot take the whole server away from gunicorn.
as_app() { sudo -H -u "$APP_USER" env CI=true COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NODE_OPTIONS=--max-old-space-size=1536 "$@"; }

[ -f "$FRONTEND_SRC/package.json" ] || fail "no frontend/package.json in ${APP_DIR}."

# The build runs on the live server next to gunicorn. A Vite build can need 1 to 1.5 GB, so refuse to start when
# less than MIN_AVAILABLE_MB (default 2048) is available. Nothing has been changed at this point.
MIN_AVAILABLE_MB="${MIN_AVAILABLE_MB:-2048}"
AVAILABLE_MB="$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)"
if [ "${AVAILABLE_MB:-0}" -lt "$MIN_AVAILABLE_MB" ]; then
  fail "only ${AVAILABLE_MB:-unknown} MB of memory is available, ${MIN_AVAILABLE_MB} MB are needed to build safely. Nothing was changed. Free memory (or add swap, which is a server change for the owner) and run again."
fi

# frontend/package.json requires node >=22.13.0: compare the full version, not only the major.
NODE_MIN="22.13.0"
node_ok() {
  command -v node >/dev/null 2>&1 || return 1
  local have
  have="$(node -p 'process.versions.node' 2>/dev/null)" || return 1
  [ "$(printf '%s\n%s\n' "$NODE_MIN" "$have" | sort -V | head -n1)" = "$NODE_MIN" ]
}

if ! node_ok; then
  echo "==> install Node ${NODE_MAJOR} (NodeSource apt repository)"
  command -v apt-get >/dev/null 2>&1 || fail "Node ${NODE_MAJOR} is missing and this is not an apt system. Install Node ${NODE_MAJOR} and run again."
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y ca-certificates curl gnupg
  install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  apt-get update -y
  apt-get install -y nodejs
fi
node_ok || fail "Node $(node -v 2>/dev/null || echo missing) found, Node ${NODE_MIN} or newer is required."

# pnpm comes from Corepack (bundled with Node 22); frontend/package.json pins the exact version.
command -v corepack >/dev/null 2>&1 || fail "corepack is missing. Install it with: npm install -g corepack"
corepack enable

echo "==> frontend: pnpm install --frozen-lockfile"
as_app pnpm --dir "$FRONTEND_SRC" install --frozen-lockfile || fail "pnpm install failed (lockfile out of date or no network)."

echo "==> frontend: vite build -> ${OUT_DIR}"
rm -rf "${OUT_DIR:?}"
as_app pnpm --dir "$FRONTEND_SRC" exec vite build --config portable/vite.config.ts || fail "vite build failed."

[ -s "$OUT_DIR/index.html" ] || fail "${OUT_DIR}/index.html is missing or empty after the build."

SUM="$(sha256sum "$OUT_DIR/index.html" | cut -d' ' -f1)"
COMMIT="$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo files)"
mkdir -p "$APP_DIR/.deploy"
LINE="$(date -u +%Y-%m-%dT%H:%M:%SZ) frontend-build commit=${COMMIT} index.html.sha256=${SUM}"
echo "$LINE" | tee -a "$APP_DIR/.deploy/deploy.log"
chown "$APP_USER":"$APP_USER" "$APP_DIR/.deploy/deploy.log" 2>/dev/null || true
