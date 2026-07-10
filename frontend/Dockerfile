# =============================================================================
# Aigenis Frontend — Production nginx image
# =============================================================================
# Serves React SPA with nginx, proxies API calls

# ---- Stage 1: Frontend build ----
FROM node:22-alpine AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---- Stage 2: Production nginx ----
FROM nginx:alpine AS production

# Install openssl for self-signed cert generation on first boot
RUN apk add --no-cache openssl

RUN mkdir -p /etc/nginx/ssl && \
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/privkey.pem \
    -out /etc/nginx/ssl/fullchain.pem \
    -subj "/CN=localhost" 2>/dev/null

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built frontend from builder
COPY --from=builder /build/dist /usr/share/nginx/html

# Helper script to symlink Let's Encrypt certs when available
RUN echo '#!/bin/sh\n\
if [ -d /etc/letsencrypt/live ]; then\n\
  DOMAIN=$(ls /etc/letsencrypt/live 2>/dev/null | head -1)\n\
  if [ -n "$DOMAIN" ] && [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then\n\
    cp -L /etc/letsencrypt/live/$DOMAIN/fullchain.pem /etc/nginx/ssl/fullchain.pem\n\
    cp -L /etc/letsencrypt/live/$DOMAIN/privkey.pem /etc/nginx/ssl/privkey.pem\n\
  fi\n\
fi\n\
exec nginx -g "daemon off;"' > /docker-entrypoint.sh && chmod +x /docker-entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

EXPOSE 80 443

ENTRYPOINT ["/docker-entrypoint.sh"]