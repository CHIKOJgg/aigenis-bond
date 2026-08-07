# Deployment Guide — Bonds Engine v4

## Prerequisites

- Docker 29+ and Docker Compose v2+
- A domain name (for HTTPS) — optional for quick start
- A Cloudflare account (optional, for tunnel)

## Quick Start (Local Development)

```bash
# 1. Clone the repo
git clone <repo-url>
cd bonds-engine

# 2. Create .env from template
cp .env.example .env

# 3. Generate secrets (optional, .env already has defaults)
python scripts/generate_secrets.py --write-env

# 4. Start all services
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
# {"status":"ok","db":"ok","version":"4.0.0"}

# 6. Open the frontend
# http://localhost
```

The API is available at `http://localhost:8000`. The frontend is served by nginx on port 80 (HTTP) and 443 (HTTPS with self-signed cert).

## Demo Instance (public, $0, read-only)

Quick start of a public demo with real MOEX data — no paid source, no bot, no payments needed:

```bash
# 1. Clone and configure env for demo mode
git clone https://github.com/CHIKOJgg/bonds-engine.git
cd bonds-engine
cp .env.example .env
```

In `.env` make sure:
```ini
DATA_SOURCE=moex
DEMO_MODE=1
AIGENIS_ENVIRONMENT=demo        # REQUIRED: production + DEMO_MODE=1 refuses to start (fail-closed paywall guard)
SEO_PUBLIC_BASE_URL=https://demo.yourdomain.com
```

```bash
# 2. Run demo stack (no paid source needed)
docker compose up -d postgres redis parser api frontend

# 3. Health check
curl -f http://localhost:8000/health
```

Public access via Cloudflare Tunnel (see below): quick tunnel
(`docker compose --profile quick-tunnel up -d cloudflared-quick`, URL in logs)
or a named tunnel with your domain.

**What works in demo mode (no auth, read-only, watermark):** `/bonds` leaderboard,
`/bonds/{id}` detail, `/partners` self-serve API key form, `/widget/top` embed,
`/calculator` YTM calculator, `/guides/*`. All data is real (MOEX ISS).
Trial partner keys are self-served; premium analysis (RV/ML) requires a paid key.
Bot commands and YooKassa are not needed (paywall returns 402 upgrade hint).

## Production Deployment

### Using Docker Compose

```bash
# 1. Set up .env with production values
cp .env.example .env
# Edit .env: set DATABASE_URL, JWT_SECRET_KEY, TELEGRAM_BOT_TOKEN, etc.

# 2. Generate strong secrets
python scripts/generate_secrets.py --write-env

# 3. Start all services
docker compose up -d

# 4. Run migrations (if needed)
docker compose exec api alembic upgrade head

# 5. Check logs
docker compose logs -f api
```

### Environment Variables

All configuration is via environment variables (see `.env.example` for the full list). Key variables:

| Variable | Description | Required |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `POSTGRES_PASSWORD` | Database password | Yes |
| `JWT_SECRET_KEY` | Min 64-char hex for HS256 | Yes |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes (for bot) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Admin credentials | Yes |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Payment processing | Optional |
| `SMTP_HOST` / `SMTP_USER` / `SMTP_PASSWORD` | Email delivery | Optional |
| `CLOUDFLARED_TUNNEL_TOKEN` | Cloudflare tunnel token | Optional |
| `DEMO_MODE` | Enable demo mode (1/true/yes) | No (default: 0) |

### Docker Compose Profiles

| Profile | Services | Use Case |
|---|---|---|
| (default) | postgres, redis, parser, api, bot, frontend, prometheus, grafana | Full production |
| `certbot` | certbot | SSL certificate management |
| `tunnel` | cloudflared | Cloudflare named tunnel (requires domain) |
| `quick-tunnel` | cloudflared-quick | Temporary trycloudflare.com URL |

Start with a profile:
```bash
docker compose --profile tunnel up -d
docker compose --profile quick-tunnel up -d
```

### SSL/TLS

**Option A: Cloudflare Tunnel (recommended)**

1. Create a tunnel at https://dash.cloudflare.com -> Access -> Tunnels
2. Copy the tunnel token
3. Set `CLOUDFLARED_TUNNEL_TOKEN` in `.env`
4. Start: `docker compose --profile tunnel up -d cloudflared`
5. In the tunnel config, point your domain to `frontend:443` with "No TLS Verify"

**Option C: ngrok (quick public URL, no account needed)**

```bash
# Install ngrok: https://ngrok.com/download
# Tunnel the API port (8000)
ngrok http 8000

# Tunnel the frontend (port 80)
ngrok http 80
```

The ngrok URL (e.g., `https://xxxx.ngrok-free.dev`) gives public HTTPS access.
Note: ngrok free tier uses a random subdomain that changes on restart.

**Option D: Cloudflare Tunnel (recommended for production)**

1. Create a tunnel at https://dash.cloudflare.com -> Access -> Tunnels
2. Copy the tunnel token
3. Set `CLOUDFLARED_TUNNEL_TOKEN` in `.env`
4. Start: `docker compose --profile tunnel up -d cloudflared`
5. In the tunnel's Public Hostname config point your domain to:
   Type=HTTPS, URL=frontend:443, and enable "No TLS Verify"

**Option B: Let's Encrypt (requires domain + port 80/443 open)**

1. Point DNS to your server
2. Start: `docker compose --profile certbot up -d certbot`
3. Start: `docker compose up -d frontend`
4. Certbot will auto-configure HTTPS

**Option C: Self-signed (development only)**

The frontend nginx generates a self-signed cert at build time. Not suitable for production.

### Resource Limits

Default resource limits (adjustable via `.env`):

| Service | RAM Limit | RAM Reserve |
|---|---|---|
| postgres | 512M | 256M |
| redis | 256M | 128M |
| parser | 2G | 1G |
| api | 512M | 256M |
| bot | 512M | 256M |
| frontend | 128M | 64M |
| prometheus | 512M | 256M |
| grafana | 256M | 128M |

## Scaling

### Horizontal Scaling (API)

The API service runs 2 uvicorn workers by default. To scale:

```bash
# Increase workers
API_WORKERS=4 docker compose up -d api
```

Or use Docker Compose replicas:
```bash
docker compose up -d --scale api=3
```

Note: With multiple API replicas, use `RATE_LIMIT_BACKEND=redis` (already the default) for distributed rate limiting.

### Database Connection Pooling

Connection pool settings (in `.env`):
- `DB_POOL_SIZE=10` — connections per API worker
- `DB_POOL_OVERFLOW=20` — additional connections on demand
- `DB_POOL_TIMEOUT=30.0` — wait timeout for a connection
- `DB_POOL_RECYCLE=3600` — recycle connections after 1 hour

## Monitoring

- **Prometheus**: `http://localhost:9090` (localhost only)
- **Grafana**: `http://localhost:3001` (localhost only, default admin/admin)
- **API metrics**: `/metrics` endpoint on each service (Prometheus format)

## Health Checks

All services have health checks configured:

```bash
docker compose ps  # Shows health status
docker compose logs -f api  # Follow API logs
```

## Backup

PostgreSQL data is persisted in the `aigenis-pgdata` Docker volume. To backup:

```bash
docker compose exec postgres pg_dump -U aigenis aigenis > backup.sql
```

## Upgrade

```bash
# Pull latest code
git pull

# Rebuild images
docker compose build

# Apply migrations
docker compose exec api alembic upgrade head

# Restart
docker compose up -d
```

## Troubleshooting

| Problem | Solution |
|---|---|
| API returns 500 | Check `docker compose logs api` |
| DB connection refused | Ensure postgres is healthy: `docker compose ps` |
| Bot not responding | Check `TELEGRAM_BOT_TOKEN` in `.env` |
| Frontend blank page | Ensure frontend build succeeded: `docker compose logs frontend` |
| SSL not working | Verify certbot or tunnel is running; check DNS |
| Rate limiting not working | Ensure `RATE_LIMIT_BACKEND=redis` and Redis is healthy |