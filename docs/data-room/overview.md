# Data Room — Bonds Engine v4

## Architecture

```
MOEX ISS (public) + market-data adapters → scraper/pipeline.py → PostgreSQL 16 → FastAPI API → React SPA
                                                                              → Telegram bot (aiogram 3)
                                                                              → Partner API
                                                                              → Widget (iframe)
                                                                              → Monte Carlo forecast
                                                                              → ML recommendations
```

- **Backend:** Python 3.13, FastAPI (async), SQLAlchemy 2.0, asyncpg, PostgreSQL 16, Redis 7
- **ML:** scikit-learn, NumPy, SciPy (Nelson-Siegel), Playwright (headless)
- **Frontend:** React 19, Vite, nginx
- **Infra:** Docker Compose (9+ services), nginx, Cloudflare Tunnel
- **Monitoring:** Prometheus + Grafana, Sentry, Loguru

## Code Metrics

| Category | Value |
|---|---|
| Python lines | ~28,000 |
| TypeScript lines | ~8,700 |
| Tests | 298 (pytest, all green) |
| Linting | ruff (blocking), mypy (non-blocking) |
| Type checking | mypy (opt-in strict) |
| CI | ruff + pytest + mypy + migrations |
| DB migrations | 24 Alembic migrations |
| Version | 4.0.0 |

## Security

- **Auth:** JWT (HS256, 30min), bcrypt, refresh tokens
- **Rate limiting:** Redis-backed distributed (100r/s API, 10r/s auth)
- **CSP:** Content-Security-Policy, X-Frame-Options DENY
- **API keys:** SHA-256 hashed, one-time display at creation
- **Webhooks:** HMAC-SHA256 signed payloads + secret token header
- **SQL:** SQLAlchemy ORM (parameterised queries)
- **Payments:** YooKassa IP whitelist + double verification + full-amount refund check
- **SSRF:** IP pinning + DNS-rebind defense + IPv6 support
- **Admin:** XFF spoofing protection (TRUSTED_PROXY mode)

## Deployment

- Docker Compose → `docker compose up -d`
- Cloudflare Tunnel for HTTPS without public IP (profiles: `tunnel`, `quick-tunnel`)
- Let's Encrypt certbot (optional, requires domain + open ports 80/443)
- Resource limits per service (configurable via `.env`)

## Modules

| Module | Description |
|---|---|
| `scraper/` | MOEX ISS parser (moex.py) + fallback source + market-data adapters |
| `api/` | FastAPI REST API + SEO (SSR) + Billing + Partner API |
| `frontend/` | React SPA + Widget + Landing Page |
| `telegram_bot/` | aiogram 3 bot (subscriptions, billing, alerts) |
| `desk/` | Fixed Income Desk (Duration, Yield Curve, RV, Carry, Repo, Stress) |
| `ml/` | ML models (YTM regression + buy/hold/wait/avoid classifier) |
| `scoring/` | Reward/Risk scoring engine |
| `portfolio/` | Portfolio manager (P&L, rebalance, optimizer) |
| `forecast/` | Monte Carlo simulation with CVaR |
| `recommendations/` | Explainable recommendations with issuer diversification |
| `monitoring/` | Prometheus metrics + change detection |
| `visualization/` | matplotlib charts |
| `notifications/` | Email/SMS alert delivery
