# =============================================================================
# Aigenis Frontend — Production nginx image
# =============================================================================
# Serves React SPA with nginx, proxies API calls

# ---- Stage 1: Frontend build ----
FROM node:22-alpine AS builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Production nginx ----
FROM nginx:alpine AS production

# Copy nginx config
COPY frontend/nginx.conf /etc/nginx/nginx.conf

# Copy built frontend from builder
COPY --from=builder /build/dist /usr/share/nginx/html

# Add non-root user
RUN addgroup -g 1001 -S nginx \
    && adduser -S -D -H -u 1001 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx \
    && chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

USER nginx

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]