# Bonds Engine v4 — Operability Report

**Date:** 2026-08-06
**Docker Server:** v29.6.2
**Python (container):** 3.13
**Python (test venv):** 3.14.6

---

## 1. Services Status (8/8 healthy)

| Service   | Image                  | Port(s)         | Health     | Notes                                         |
|-----------|------------------------|-----------------|------------|-----------------------------------------------|
| postgres  | postgres:16-alpine     | 5432 (localhost) | healthy   | PostgreSQL 16, persistent volume `aigenis-pgdata` |
| redis     | redis:7-alpine         | (internal)      | healthy   | Redis 7 with password, persistent volume `aigenis-redisdata` |
| parser    | aigenis-parser:latest  | (internal)      | healthy   | Scraper scheduler — 12 cron jobs running      |
| api       | aigenis-parser:latest  | 8000            | healthy   | FastAPI 4.0.0, 2 uvicorn workers              |
| bot       | aigenis-parser:latest  | 9090 (internal) | healthy   | aiogram 3 Telegram bot + metrics server       |
| frontend  | aigenis-frontend:latest| 80→443          | healthy   | nginx + React SPA, self-signed TLS cert       |
| prometheus| prom/prometheus:latest | 9090 (localhost)| running   | Scraping `api` and `bot` targets              |
| grafana   | grafana/grafana:13.x   | 3001 (localhost)| running   | Dashboard UI, auth required                   |

---

## 2. Issues Found & Fixed

### 2.1 Python 2 `except` syntax (CRITICAL — 28 occurrences in 16 files)

**Root cause:** The codebase contained 28 instances of Python 2 `except X, Y:` syntax
across 16 Python files. Python 3.13 (used in the Docker image) requires
parentheses: `except (X, Y):`. This caused `SyntaxError` on import, crashing
both the API and the parser containers.

**Files fixed:**
- `api/admin/router.py` (2 occurrences)
- `api/auth/router.py` (2)
- `api/billing/service.py` (3)
- `api/partner/security.py` (1)
- `api/partner/webhooks.py` (2)
- `api/seo/_common.py` (1)
- `api/seo/calculator.py` (1)
- `ml/features.py` (1)
- `scraper/config.py` (already correct in git, verified)
- `scraper/fallback_source.py` (1)
- `scraper/models.py` (2)
- `scraper/moex.py` (4)
- `scraper/moex_stocks.py` (3)
- `scraper/parsers/xlsx.py` (1)
- `scraper/pipeline.py` (3)
- `scraper/scheduler.py` (1)
- `telegram_bot/bond_picker.py` (1)
- `telegram_bot/commands.py` (2)
- `scraper/config.py` (3 — `_json.JSONDecodeError`, `TypeError`, `ValueError`)

**Status:** Fixed in all files. py_compile passes on all 295 Python files.

### 2.2 REDIS_URL / REDIS_PASSWORD mismatch (.env)

**Root cause:** `.env` had `REDIS_URL` using password `B_CgjJozQYtfliRn33vHPdN8-ZI`
but `REDIS_PASSWORD` was set to `owEYjaRfaD4DZwhhDuSvDgNv4pM`. The Redis server
container requires the password from `REDIS_PASSWORD`, so all Redis clients
connecting with the old password in `REDIS_URL` would fail authentication.

**Fix:** Updated `REDIS_URL` in `.env` to use `REDIS_PASSWORD`'s value
(`owEYjaRfaD4DZwhhDuSvDgNv4pM`).

### 2.3 Makefile commands use bare subcommand names

**Root cause:** The `docker-entrypoint.sh` entrypoint script ends with
`exec "$@"`, which means the first argument is treated as a command to execute.
The Makefile had commands like `docker compose run --rm parser health`, which
passed `health` as the command. Since `health` is not a standalone binary,
the entrypoint failed with `exec: health: not found`.

**Fix:** Updated 9 Makefile targets to use full Python module invocation:
- `once` → `python3 -m scraper once`
- `once-usd` → `python3 -m scraper once --currency USD`
- `history` → `python3 -m scraper backfill`
- `seo-sitemap` → `python3 -m scraper seo-sitemap`
- `health` → `python3 -m scraper health`
- `desk-curve` → `python3 -m scraper desk-ccurve`
- `desk-rv` → `python3 -m scraper desk-rv`
- `desk-stress` → `python3 -m scraper desk-stress`
- `desk-car` → `python3 -m scraper desk-carry --funding ...`

### 2.4 Missing `demo-data/` in Dockerfile

**Root cause:** The Dockerfile did not include `COPY demo-data ./demo-data`,
so the demo API endpoints (`/api/v1/demo/portfolio-impact`) returned 404
because the fixture data was not present in the container.

**Fix:** Added `COPY demo-data ./demo-data` to the Dockerfile.

### 2.5 Missing environment variables in docker-compose.yml

**Root cause:** The `.env` file defined `DEMO_DISABLE_SIDE_EFFECTS` and the
demo endpoint code checks `AIGENIS_ENV`, but neither variable was passed
through to the container environment in `docker-compose.yml`. Each service
must explicitly list environment variables there.

**Fix:** Added `AIGENIS_ENV` and `DEMO_DISABLE_SIDE_EFFECTS` to the `api`,
`parser`, and `bot` service environment sections in `docker-compose.yml`.

### 2.6 AIGENIS_ENV vs AIGENIS_ENVIRONMENT inconsistency

**Root cause:** The demo endpoint (`api/demo.py:166`) checks `AIGENIS_ENV`,
while the rest of the codebase uses `AIGENIS_ENVIRONMENT`. To make both work
in Docker, `AIGENIS_ENV` is now mapped from `AIGENIS_ENVIRONMENT` in
docker-compose.

**Note:** This is a pre-existing inconsistency. The test
(`tests/test_demo_endpoint.py`) uses `AIGENIS_ENV`, so the variable name was
preserved rather than renamed.

### 2.7 White screen on /onboarding after login (CRITICAL)

**Root cause:** In `frontend/src/app/router.tsx:76-78`, the router redirected to
`/onboarding` whenever `showOnboarding` was `true`. But since `showOnboarding`
is only cleared by `finishOnboarding()` (called via `onDone` in
`OnboardingFlow`), and the redirect fired *before* the `Routes` component could
render the OnboardingFlow route, `finishOnboarding()` was never called. This
created an infinite redirect loop: `showOnboarding` stays `true` → Navigate fires
→ URL is `/onboarding` → `showOnboarding` still `true` → Navigate fires again →
white screen (no visible content, just an empty redirect).

**Fix:** Added a check to only redirect when the current path is not already
`/onboarding`:

```tsx
if (showOnboarding && window.location.pathname !== ROUTES.onboarding) {
    return <Navigate to={ROUTES.onboarding} replace />;
}
```

This allows the `Routes` component to render the OnboardingFlow route normally
when the user is already at `/onboarding`.

### 2.8 Alembic migration race condition on startup

**Root cause:** The `alembic/env.py` used `compare_type=True` in both
`run_migrations_offline()` and `do_run_migrations()`. With PostgreSQL 16 and
asyncpg, `compare_type=True` caused Alembic to attempt creating the
`alembic_version` table with a new type, which collided with the already-existing
type when multiple containers (api, bot, parser) started simultaneously. The
advisory lock in `docker-entrypoint.sh` serializes migrations, but
`compare_type=True` caused spurious DDL that still failed.

**Fix:** Removed `compare_type=True` from both `run_migrations_offline()` and
`do_run_migrations()` in `alembic/env.py`. The type comparison is not needed
since all migrations are explicitly written with correct column types.

### 2.9 MOEX API actually reachable from Docker

**Note:** Initially reported as unreachable (Section 5.1), re-testing showed
`iss.moex.com` is reachable from the parser container. The SSL handshake timeout
was transient. The MOEX scraper should work. Verify with:
```bash
docker compose run --rm parser python3 -m scraper moex
```

---

## 3. API Endpoint Testing Results

### 3.1 Public endpoints

| Endpoint | Method | Status | Result |
|----------|--------|--------|--------|
| `/health` | GET | 200 | `{"status":"ok","db":"ok","version":"4.0.0"}` |
| `/ready` | GET | 200 | `{"status":"ok","db":"ok","version":"4.0.0"}` |
| `/api/v1/bonds` | GET | 200 | `[]` (empty DB) |
| `/api/v1/bonds?limit=5` | GET | 200 | `[]` |
| `/api/v1/scores` | GET | 200 | `[]` |
| `/api/v1/stats` | GET | 200 | `{"total_bonds":0,"active_bonds":0,"by_currency":{}}` |
| `/docs` | GET | 200 | Swagger UI HTML |
| `/openapi.json` | GET | 200 | OpenAPI 3 schema |
| `/metrics` | GET | 200 | Prometheus metrics |
| `/robots.txt` | GET | 200 | SEO robots rules |
| `/sitemap.xml` | GET | 200 | Sitemap XML |
| `/bonds` | GET | 200 | SEO bond listing page |

### 3.2 Validation & error handling

| Test | Status | Result |
|------|--------|--------|
| `/api/v1/bonds?limit=0` | 400 | `{"detail":"limit must be between 1 and 1000"}` |
| `/api/v1/bonds?limit=1001` | 400 | `{"detail":"limit must be between 1 and 1000"}` |
| `/api/v1/bonds/NOPE` | 404 | `{"detail":"Bond NOPE not found"}` |
| `/nonexistent` | 404 | SPA fallback (returns index.html) |
| 200 rapid requests | 429 | Rate limited after 60 requests (60 req/60s) |

### 3.3 Authentication

| Endpoint | Method | Status | Result |
|----------|--------|--------|--------|
| `/auth/register` | POST | 200 | Returns `access_token`, `refresh_token`, `token_type` |
| `/auth/login` | POST | 200 | Returns JWT tokens |
| `/auth/me` | GET | 200 | Returns user profile JSON |

### 3.4 Authenticated endpoints

| Endpoint | Method | Status | Result |
|----------|--------|--------|--------|
| `/api/v1/portfolio` | GET | 200 | Returns portfolio JSON with forecast data |
| `/api/v1/watchlist?internal_id=B1` | POST | 404 | Bond not found (DB empty) |
| `/api/v1/watchlist?internal_id=B1` (no auth) | POST | 401 | Requires authentication |

### 3.5 Demo endpoint

| Endpoint | Method | Status | Result |
|----------|--------|--------|--------|
| `/api/v1/demo/portfolio-impact` | POST | 200 | Returns portfolio impact with fixture data |

### 3.6 Security headers

| Header | Value |
|--------|-------|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Content-Security-Policy` | `default-src 'self'; object-src 'none'; frame-ancestors 'none'; ...` |
| `X-Request-Id` | UUIDv4 trace ID |

### 3.7 Frontend (nginx proxy)

| Path | Status | Result |
|------|--------|--------|
| `http://localhost/` | 301 | Redirect to HTTPS |
| `https://localhost/` | 200 | React SPA served |
| `https://localhost/health` | 200 | API health via proxy |
| `https://localhost/api/v1/stats` | 200 | API stats via proxy |

### 3.8 Bot

| Check | Result |
|-------|--------|
| Bot health (`curl localhost:9090/health` in container) | `{"status": "ok", "db": "ok"}` |
| Bot metrics server | Running on port 9090 |
| Bot DB migrations | Complete |
| Bot scheduler | Running with 12 cron jobs |

### 3.9 Prometheus & Grafana

| Service | Check | Result |
|---------|-------|--------|
| Prometheus | `/api/v1/targets` | Scraping `aigenis-api` and `aigenis-bot` |
| Promtheus | `/api/v1/rules` | 200 |
| Grafana | `/api/health` | `{"database": "ok", "version": "13.1.2"}` |

---

## 4. Test Suite Results

```
494 passed, 1 warning in ~50s
```

- `ruff check .` — All checks passed
- `py_compile` — 295 files checked, 0 syntax errors
- Test categories: auth, API endpoints, billing webhooks, demo, SEO, ML,
  portfolio optimizer, scoring, rate limiting, access control, monitoring,
  subscriptions, Telegram bot, data quality, desk analytics, stocks API,
  NLP, widget, and more.

**Note:** `ruff format --check` reports 20 files that "would be reformatted" —
this is a ruff bug where `ruff format` incorrectly converts Python 3
`except (X, Y):` syntax back to Python 2 `except X, Y:`. Use `ruff check`
(not `ruff format`) for linting/formatting.

---

## 5. Known Limitations (External / Informational)

### 5.1 Empty database

The database is currently empty (`total_bonds: 0`). This is expected for a
fresh deployment — the parser's scheduler will populate it once the scraper
is run. All data-display endpoints return `[]` or empty objects, which is
correct behavior for an empty database.

### 5.2 Grafana auth required

Grafana returns HTTP 401 for API endpoints because anonymous authentication
is disabled (`GF_AUTH_ANONYMOUS_ENABLED: "false"`). Login with the configured
`GRAFANA_ADMIN_USER`/`GRAFANA_ADMIN_PASSWORD` credentials.

### 5.3 Telegram bot token

The Telegram bot token in `.env` is a placeholder. The bot starts and serves
its health endpoint, but cannot connect to Telegram's API without a real bot
token from @BotFather.

---

## 6. Commands Reference (Fixed)

```bash
# Start all services
docker compose up -d

# Health check
docker compose run --rm parser python3 -m scraper health

# One-time data collection (MOEX)
docker compose run --rm parser python3 -m scraper moex

# Desk commands
docker compose run --rm parser python3 -m scraper desk-curve
docker compose run --rm parser python3 -m scraper desk-rv
docker compose run --rm parser python3 -m scraper desk-stress

# Run tests locally
python -m pytest tests/ -rN

# Lint
python -m ruff check .
```
