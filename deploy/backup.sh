#!/usr/bin/env bash
# Nightly PostgreSQL + uploads backup. Installed to /etc/cron.d/flowly-backup by ec2-setup.sh.
# Keeps 14 days in /var/backups/flowly. Copy these off the server (S3, rsync) for real disaster recovery.
set -euo pipefail
DEST="${BACKUP_DIR:-/var/backups/flowly}"
MEDIA_DIR="${MEDIA_DIR:-/var/www/flowly-media}"
DB_NAME="${DB_NAME:-flowly}"
STAMP="$(date +%F-%H%M)"
umask 077
mkdir -p "$DEST"
sudo -u postgres pg_dump -Fc "$DB_NAME" > "$DEST/db-$STAMP.dump"
tar czf "$DEST/media-$STAMP.tgz" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")" 2>/dev/null || true
find "$DEST" -type f -mtime +14 -delete
echo "backup ok: $DEST (db-$STAMP.dump)"
# Restore:  sudo -u postgres pg_restore -c -d flowly /var/backups/flowly/db-<stamp>.dump