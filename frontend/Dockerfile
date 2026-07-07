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

# Copy nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built frontend from builder
COPY --from=builder /build/dist /usr/share/nginx/html

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]