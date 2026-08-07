# Architecture — Bonds Engine v4

## Overview

Bonds Engine is a monorepo Python + React application deployed via Docker Compose. It follows a layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React SPA + nginx)                          │
│  Serves static assets, proxies /api/ → API service     │
├─────────────────────────────────────────────────────────┤
│  API (FastAPI, uvicorn, 2 workers)                     │
│  REST endpoints, auth, billing, webhooks               │
├─────────────────────────────────────────────────────────┤
│  Parser (scraper + scheduler + analytics)              │
│  Data collection, backfill, ML training, monitoring    │
├─────────────────────────────────────────────────────────┤
│  Bot (aiogram 3 Telegram bot)                          │
│  User interactions, subscriptions, alerts, commands    │
├─────────────────────────────────────────────────────────┤
│  PostgreSQL 16 + Redis 7                               │
│  Primary DB + cache + rate-limiting + task queue       │
├─────────────────────────────────────────────────────────┤
│  Observability: Prometheus + Grafana                   │
│  Metrics, dashboards, alerting                         │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Data Collection
```
MOEX ISS / market-data adapters → scraper/pipeline.py → scraper/db.py (asyncpg)
                                                    ↓
                                             bonds table + history table
```

### 2. Scoring & Recommendations
```
bonds + history → scoring/engine.py → Reward/Risk scores
                                       ↓
                              recommendations/engine.py
                              (diversification, explainability)
                                       ↓
                              ML model (ml/engine.py)
                              (walk-forward CV, combined regressor+classifier)
                                       ↓
                              forecast/engine.py (Monte Carlo + CVaR)
                                       ↓
                              portfolio/optimizer.py (Calmar ratio, YTM-weighted)
```

### 3. Telegram Bot
```
User → Telegram → telegram_bot/bot.py → aiogram 3 handlers
                                          ↓
                                    command/query → API or DB
                                          ↓
                                    Response (text/inline keyboard)
```

### 4. API Requests
```
Client → nginx (443) → api:8000 → FastAPI router → service → DB/Redis
```

## Key Design Decisions

### Dialect-agnostic database access
All SQLAlchemy operations use dialect-agnostic patterns. The `upsert_predictions` function uses `upsert_row` instead of PostgreSQL-specific `pg_insert`, ensuring compatibility with SQLite (dev/tests) and PostgreSQL (production).

### Unique constraint on predictions
Migration `0023_predictions_unique` adds a UNIQUE constraint on `(internal_id, asof_date, model_version, kind)` to prevent duplicate prediction rows from concurrent training runs.

### Monte Carlo forecast
The forecast engine uses a deterministic approach when volatility is zero (fast path) and switches to Monte Carlo simulation when volatility is detected. This provides p5/p25/p50/p75/p95 percentiles and CVaR_95 for risk-aware decision making.

### Walk-forward ML validation
Instead of a simple train/test split, the ML engine uses walk-forward cross-validation where each fold's training data is strictly before the validation data in time. This prevents lookahead bias and gives realistic out-of-time MAE estimates.

### Webhook security
- Telegram webhooks: HMAC secret token + `X-Telegram-Bot-Api-Secret-Token` header
- Partner webhooks: HMAC signature + secret returned once at creation
- YooKassa webhooks: IP filtering + API re-verification of every event
- Admin endpoints: XFF spoofing protection (TRUSTED_PROXY mode)

### SSRF protection
Webhook URL validation includes IP pinning (resolve hostname to IP, compare against allowlist) with IPv6 support. DNS-rebind attacks are prevented by resolving at registration time and pinning.

## Module Responsibilities

| Module | Responsibility | Key Files |
|---|---|---|
| `scraper/` | Data ingestion, MOEX/AIGENIS parsing, scheduling | `pipeline.py`, `parsers/`, `db.py` |
| `scoring/` | Reward/Risk scoring engine | `engine.py`, `repository.py`, `models.py` |
| `portfolio/` | P&L calculation, rebalancing, optimization | `pnl.py`, `rebalance.py`, `optimizer.py` |
| `forecast/` | Monte Carlo simulation with CVaR | `engine.py` |
| `ml/` | Feature engineering, training, prediction | `engine.py`, `features.py`, `repository.py`, `models.py` |
| `recommendations/` | Explainable bond recommendations | `engine.py` |
| `desk/` | Fixed income analytics (duration, yield curve, RV, carry, repo, stress) | `duration.py`, `yield_curve.py`, `relative_value.py`, `carry.py`, `repo.py`, `stress.py` |
| `api/` | REST API, auth, billing, webhooks | `main.py`, routers in `api/` |
| `telegram_bot/` | Telegram bot, subscriptions, billing | `bot.py`, `subscriptions.py`, `billing.py` |
| `monitoring/` | Prometheus metrics, change detection | `engine.py` |
| `alembic/` | Database migrations | `versions/` |

## Deployment Topology

All services run in a single Docker network (`aigenis-net`):

- `postgres:5432` — PostgreSQL 16
- `redis:6379` — Redis 7
- `parser` — Scraper + scheduler (2G RAM limit)
- `api` — FastAPI on port 8000 (512M RAM limit)
- `bot` — Telegram bot (512M RAM limit)
- `frontend` — nginx serving React SPA on 80/443 (128M RAM limit)
- `prometheus` — Metrics collection (localhost:9090)
- `grafana` — Dashboards (localhost:3001)
- `cloudflared` (optional) — Cloudflare Tunnel for HTTPS without port forwarding

## Security Boundaries

```
Internet → Cloudflare (optional) → nginx (TLS termination) → API
                                                              ↓
                                                    Auth middleware
                                                              ↓
                                                    Rate limiting (Redis)
                                                              ↓
                                                    Business logic → DB
```

- API is never exposed directly to the internet (always behind nginx or tunnel)
- PostgreSQL and Redis are bound to internal Docker network only
- Prometheus and Grafana are bound to localhost only
- All secrets are injected via environment variables (never hardcoded)