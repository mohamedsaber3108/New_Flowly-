#!/usr/bin/env bash
# Quick production health report: services, response codes, recent errors, resources, backups, TLS.
# Usage: sudo bash /var/www/flowly/deploy/status-report.sh
set -uo pipefail
echo "== services";  systemctl is-active gunicorn nginx postgresql | paste -sd' '
echo "== HTTP status codes (current nginx access log)"
awk '{print $9}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -n 8
echo "== last 5xx / 499 responses"
awk '$9 ~ /^(5[0-9][0-9]|499)$/' /var/log/nginx/access.log | tail -n 5 | cut -c1-180
echo "== upstream (Gunicorn) connection errors in nginx error log"
grep -c 'while reading response header from upstream' /var/log/nginx/error.log || true
echo "== application errors in the last 24h"
journalctl -u gunicorn --since '24 hours ago' --no-pager | grep -cE ' ERROR | CRITICAL ' || true
echo "== resources"; free -m | sed -n 2p; df -h / | tail -n 1
echo "== latest backups"; ls -1t /var/backups/flowly 2>/dev/null | head -n 2
CERT=$(ls -d /etc/letsencrypt/live/*/ 2>/dev/null | grep -v README | head -n 1)
[ -n "$CERT" ] && { echo "== TLS certificate"; openssl x509 -in "${CERT}fullchain.pem" -noout -subject -enddate; }
