#!/usr/bin/env bash
# =============================================================================
# Flowly - Let's Encrypt certificate via Certbot (free, auto-renewing).
# Prerequisite: DNS A records for DOMAIN and www.DOMAIN point at this server and ec2-setup.sh has run.
#
#   sudo DOMAIN=yourdomain.com LE_EMAIL=you@yourdomain.com bash deploy/ssl-setup.sh
# Set INCLUDE_WWW=0 if www.DOMAIN has no DNS record.
# =============================================================================
set -euo pipefail

: "${DOMAIN:?Set DOMAIN, e.g. yourdomain.com}"
LE_EMAIL="${LE_EMAIL:-}"   # recommended: expiry notices go here
INCLUDE_WWW="${INCLUDE_WWW:-1}"
SNIPPET=/etc/nginx/snippets/flowly-ssl.conf

[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get install -y certbot python3-certbot-nginx cron
mkdir -p /var/www/certbot

EMAIL_ARGS=(--register-unsafely-without-email)
[ -n "$LE_EMAIL" ] && EMAIL_ARGS=(-m "$LE_EMAIL")
DOMAINS=(-d "$DOMAIN")
[ "$INCLUDE_WWW" = "1" ] && DOMAINS+=(-d "www.${DOMAIN}")

# 'certonly --webroot' keeps our hand-written nginx.conf untouched (the --nginx installer would rewrite it).
certbot certonly --webroot -w /var/www/certbot "${DOMAINS[@]}" \
  --non-interactive --agree-tos "${EMAIL_ARGS[@]}" --cert-name "$DOMAIN" --keep-until-expiring

cat > "$SNIPPET" <<EOF
ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
EOF
nginx -t
systemctl reload nginx

# Renewal: reload nginx after each successful renewal, and run twice daily from cron.
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'EOF'
#!/usr/bin/env bash
systemctl reload nginx
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

cat > /etc/cron.d/flowly-certbot <<'EOF'
# Flowly: attempt certificate renewal twice a day (certbot only renews within 30 days of expiry).
17 3,15 * * * root certbot renew --quiet
EOF
chmod 644 /etc/cron.d/flowly-certbot

certbot renew --dry-run
echo
echo "SSL is live: https://${DOMAIN}/   (auto-renewal: cron + certbot.timer)"
