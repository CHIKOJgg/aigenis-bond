# Bonds Engine v4 — Fixed Income Analytics Platform

**Bonds Engine** is a production-grade fixed income analytics platform for Russian and international bond markets. It combines automated data collection, ML-driven forecasts, portfolio optimization, and a Telegram bot — all behind a REST API with a React frontend.

## What it does

| Capability | Module |
|---|---|
| Bond data collection (MOEX ISS) | `scraper/` |
| Reward/Risk scoring | `scoring/` |
| Portfolio P&L, rebalancing, optimization | `portfolio/` |
| Monte Carlo forecast with CVaR | `forecast/` |
| ML walk-forward training + buy/hold/wait/avoid | `ml/` |
| Yield curve (Nelson-Siegel), duration, carry, stress | `desk/` |
| Explainable recommendations with issuer diversification | `recommendations/` |
| REST API + React SPA | `api/` + `frontend/` |
| Telegram bot with subscriptions, billing, alerts | `telegram_bot/` |
| Monitoring, alerting, Prometheus/Grafana | `monitoring/` |

## Quick start (Docker)

```bash
# 1. Copy .env and fill in secrets
cp .env.example .env

# 2. Start all services
docker compose up -d

# 3. Verify
curl http://localhost:8000/health
# {"status":"ok","db":"ok","version":"4.0.0"}

# 4. Open the frontend
# http://localhost  (nginx proxies API at /api/)
```

## Key features (v4)

- **Monte Carlo forecast** — p5/p25/p50/p75/p95 percentiles + CVaR_95
- **Calmar ratio** in portfolio optimizer (real YTM-weighted expected return)
- **Walk-forward CV** for ML model validation
- **Issuer diversification** — max 2 bonds per issuer in recommendations
- **Webhook HMAC secret** for Telegram and partner webhooks
- **SSRF protection** with IP pinning + IPv6 support
- **Refund validation** — full-amount only, cross-channel protection
- **298 tests**, all green, ruff-clean

## Project structure

```
bonds-engine/
├── api/              FastAPI REST API + routers
├── scraper/          Data collection (MOEX, AIGENIS, fallback)
├── desk/             Fixed income analytics (duration, yield curve, RV, carry, repo, stress)
├── forecast/         Monte Carlo simulation engine
├── ml/               ML training, features, walk-forward CV, predictions
├── portfolio/        P&L, rebalancing, optimizer
├── recommendations/  Explainable bond recommendations
├── scoring/          Reward/Risk scoring engine
├── telegram_bot/     aiogram 3 Telegram bot (subscriptions, billing, alerts)
├── monitoring/       Prometheus metrics, change detection
├── visualization/    matplotlib charts
├── notifications/    Email/SMS alert delivery
├── alembic/          DB migrations
├── frontend/         React SPA + nginx
├── tests/            pytest suite (298)
├── docker-compose.yml  Full stack (postgres, redis, parser, api, bot, frontend)
├── Dockerfile          Multi-stage production image
└── README.md           This file
```

## Tech stack

- **Python 3.13**, FastAPI, SQLAlchemy 2.0, asyncpg
- **scikit-learn**, scipy, pandas, numpy
- **aiogram 3** (Telegram bot)
- **React 18**, Vite, nginx (frontend)
- **PostgreSQL 16**, Redis 7
- **Playwright** (headless browser for scraper)
- **Docker**, Docker Compose

## License

Proprietary — AIGENIS INVEST
