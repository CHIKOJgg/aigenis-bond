#!/bin/sh
set -e

# If Let's Encrypt certs are mounted (certbot profile), symlink them over the
# build-time self-signed certs so nginx serves the real certificate.
# Symlinks (not copies) are used so `nginx -s reload` after `certbot renew`
# picks up the rotated cert automatically.
if [ -d /etc/letsencrypt/live ]; then
  DOMAIN=$(ls /etc/letsencrypt/live 2>/dev/null | head -1)
  if [ -n "$DOMAIN" ] && [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    ln -sf "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" /etc/nginx/ssl/fullchain.pem
    ln -sf "/etc/letsencrypt/live/$DOMAIN/privkey.pem"  /etc/nginx/ssl/privkey.pem
  fi
fi

# Hand off to the official nginx entrypoint (runs config test + execs CMD).
exec /docker-entrypoint.sh "$@"
