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
RUN npx vite build

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
COPY nginx-spa.conf /etc/nginx/nginx-spa.conf

# Copy built frontend from builder
COPY --from=builder /build/dist /usr/share/nginx/html

# Entrypoint: symlink Let's Encrypt certs (if mounted) then run official nginx entrypoint
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -fk --max-time 5 https://localhost/health || exit 1

EXPOSE 80 443

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]