# Quick Start Guide — Bonds Engine v4

Get Bonds Engine running in 5 minutes.

## 1. Prerequisites

- Docker and Docker Compose installed
- A terminal (PowerShell on Windows, bash on Linux/Mac)

## 2. Clone and Configure

```bash
git clone <repo-url>
cd bonds-engine
cp .env.example .env
```

Edit `.env` and set at minimum:
- `POSTGRES_PASSWORD` — a strong password
- `TELEGRAM_BOT_TOKEN` — from @BotFather (optional for API-only use)
- `JWT_SECRET_KEY` — a random 64+ char hex string

Or generate all secrets automatically:
```bash
python scripts/generate_secrets.py --write-env
```

## 3. Start the Stack

```bash
docker compose up -d
```

This starts:
- PostgreSQL (database)
- Redis (cache + rate limiting)
- Parser (data collection + ML training)
- API (REST API on port 8000)
- Bot (Telegram bot)
- Frontend (React SPA on nginx, ports 80/443)
- Prometheus + Grafana (monitoring)

## 4. Verify

```bash
# Check all services are running
docker compose ps

# Test the API
curl http://localhost:8000/health
# {"status":"ok","db":"ok","version":"4.0.0"}

# Open the frontend
# Browser: http://localhost
```

## 5. Try It Out

1. **Browse bonds**: http://localhost/bonds
2. **Check top scores**: http://localhost/top
3. **View recommendations**: http://localhost/recommendations
4. **Run a forecast**: Use the calculator at http://localhost/calculator
5. **Telegram bot**: Find your bot and send `/start`

## 6. Stop the Stack

```bash
docker compose down
```

## 7. Next Steps

| Task | Guide |
|---|---|
| Configure HTTPS | [DEPLOYMENT.md](DEPLOYMENT.md) |
| Set up Cloudflare tunnel | [DEPLOYMENT.md](DEPLOYMENT.md#cloudflare-tunnel) |
| Customize scoring | [DEVELOPMENT.md](DEVELOPMENT.md) |
| Add a new endpoint | [DEVELOPMENT.md](DEVELOPMENT.md#adding-a-new-endpoint) |
| Monitor with Grafana | [OPERATIONS.md](OPERATIONS.md) |
| Full API reference | [API.md](API.md) |
| System architecture | [architecture.md](architecture.md) |

## Common Commands

```bash
# View logs
docker compose logs -f api

# Run a one-off command
docker compose exec api python -m scraper desk-curve

# Apply database migrations
docker compose exec api alembic upgrade head

# Restart a service
docker compose restart api

# Update to latest code
git pull && docker compose build && docker compose up -d
```

## Troubleshooting

If `curl http://localhost:8000/health` returns an error:
1. Check that all containers are running: `docker compose ps`
2. Check the API logs: `docker compose logs api`
3. Verify `.env` has correct `DATABASE_URL` and `POSTGRES_PASSWORD`
4. Wait 30 seconds — PostgreSQL takes time to start