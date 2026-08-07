# API Reference — Bonds Engine v4

Base URL: `https://your-domain.com/api/v1` (or `http://localhost:8000/api/v1` in dev)

All endpoints return JSON unless otherwise noted. Authentication is via Bearer token in the `Authorization` header (except public endpoints).

## Public Endpoints (no auth required)

### Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check with DB connectivity and version |
| `GET` | `/ready` | Readiness probe (checks all dependencies) |

### SEO (public pages)

| Method | Path | Description |
|---|---|---|
| `GET` | `/bonds` | Bond listing page (SSR) |
| `GET` | `/bonds/{internal_id}` | Bond detail page (SSR) |
| `GET` | `/sitemap.xml` | XML sitemap |
| `GET` | `/robots.txt` | Robots.txt |
| `GET` | `/partners` | Partners landing page |
| `POST` | `/partners/request` | Request a partner key |
| `GET` | `/guides` | Guides index |
| `GET` | `/guides/{slug}` | Guide detail page |
| `GET` | `/calculator` | Bond calculator page |

### Pricing

| Method | Path | Description |
|---|---|---|
| `GET` | `/pricing` | Public pricing page |

### Widget (public embed)

| Method | Path | Description |
|---|---|---|
| `GET` | `/widget/top` | Top bonds widget (JSON) |
| `GET` | `/widget/embed.js` | Embed script for partner sites |

### Stocks (public)

| Method | Path | Description |
|---|---|---|
| `GET` | `/stocks/stats` | Market-wide statistics |
| `GET` | `/stocks/sectors` | Sector list |
| `GET` | `/stocks/{internal_id}` | Stock detail |
| `GET` | `/stocks/{internal_id}/history` | OHLCV history |
| `GET` | `/stocks/board/{board}` | Bonds by MOEX board |
| `GET` | `/stocks/top/dividend` | Top dividend stocks |
| `GET` | `/stocks/top/cap` | Top market cap stocks |
| `GET` | `/stocks/search/{query}` | Search stocks |

### Bonds (public)

| Method | Path | Description |
|---|---|---|
| `GET` | `/bonds` | List all bonds (paginated) |
| `GET` | `/bonds/{internal_id}` | Bond detail by internal ID |

### Scores (public)

| Method | Path | Description |
|---|---|---|
| `GET` | `/scores` | List all scores |

### Stats (public)

| Method | Path | Description |
|---|---|---|
| `GET` | `/stats` | Platform statistics |

---

## Authenticated Endpoints

All authenticated endpoints require `Authorization: Bearer <token>`.

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Register new user |
| `POST` | `/auth/login` | Login (email + password) |
| `POST` | `/auth/refresh` | Refresh access token |
| `POST` | `/auth/google` | Google OAuth login |
| `POST` | `/auth/forgot-password` | Request password reset email |
| `POST` | `/auth/reset-password` | Reset password with token |
| `POST` | `/auth/verify-email` | Verify email with token |
| `GET` | `/auth/me` | Get current user profile |

### Portfolio

| Method | Path | Description |
|---|---|---|
| `GET` | `/portfolio` | Full portfolio view (positions + P&L) |
| `GET` | `/portfolio/plan` | Portfolio plan (target allocation) |
| `GET` | `/portfolio/income` | Income breakdown |
| `GET` | `/portfolio/pnl` | P&L summary |
| `GET` | `/portfolio/pnl/history` | P&L history over time |
| `POST` | `/portfolio/transactions` | Record a buy/sell transaction |
| `GET` | `/portfolio/transactions` | List transactions |
| `POST` | `/portfolio/backtest` | Run a backtest |
| `POST` | `/positions` | Add a position |
| `GET` | `/positions` | List all positions |
| `DELETE` | `/positions/{internal_id}` | Remove a position |
| `POST` | `/rebalance` | Execute portfolio rebalance |

### Analytics & Scoring

| Method | Path | Description |
|---|---|---|
| `GET` | `/top` | Top bonds by reward/risk score |
| `GET` | `/subscribe-info` | Subscription tier info for current user |
| `GET` | `/bonds/currency/{currency}` | Bonds filtered by currency |
| `GET` | `/bond/{internal_id}` | Bond card with full analytics |
| `GET` | `/search` | Search bonds |
| `GET` | `/companies` | List all issuers |
| `GET` | `/companies/{issuer}` | Issuer detail |

### Desk Analytics

| Method | Path | Description |
|---|---|---|
| `GET` | `/desk/curve` | Nelson-Siegel yield curve |
| `GET` | `/desk/duration` | Duration analysis |
| `GET` | `/desk/rv` | Relative value (rich/cheap) |
| `GET` | `/desk/carry` | Carry analysis |
| `POST` | `/desk/repo` | Repo calculation |
| `GET` | `/desk/stress` | Stress test results |
| `GET` | `/desk/spreads` | Yield spreads between bonds |
| `GET` | `/desk/status` | Desk engine status |

### ML & Forecast

| Method | Path | Description |
|---|---|---|
| `GET` | `/ml/status` | ML model status and metrics |
| `GET` | `/ml/predict/{bond_id}` | ML prediction for a bond |
| `GET` | `/forecast` | Monte Carlo forecast (p5/p25/p50/p75/p95 + CVaR) |
| `GET` | `/scenarios` | What-if scenarios |

### Recommendations

| Method | Path | Description |
|---|---|---|
| `GET` | `/recommendations` | Explainable bond recommendations |

### Watchlist

| Method | Path | Description |
|---|---|---|
| `POST` | `/watchlist` | Add bond to watchlist |
| `DELETE` | `/watchlist/{internal_id}` | Remove from watchlist |

### Alerts

| Method | Path | Description |
|---|---|---|
| `POST` | `/alerts/rules` | Create alert rule |
| `GET` | `/alerts/rules` | List alert rules |
| `GET` | `/alerts/feed` | Alert feed |
| `GET` | `/alerts` | List alerts |

### Portfolio Planning

| Method | Path | Description |
|---|---|---|
| `POST` | `/build_plan` | Build a portfolio plan |
| `POST` | `/allocate` | Allocate capital across bonds |

---

## Partner API

All partner endpoints require a partner API key in the `X-Partner-Key` header.

| Method | Path | Description |
|---|---|---|
| `POST` | `/partner/keys` | Create a partner API key |
| `GET` | `/partner/keys` | List partner keys |
| `DELETE` | `/partner/keys/{key_id}` | Revoke a partner key |
| `GET` | `/partner/referrals` | Referral statistics |
| `POST` | `/partner/webhooks` | Create a webhook endpoint |
| `GET` | `/partner/webhooks` | List webhooks |
| `DELETE` | `/partner/webhooks/{webhook_id}` | Remove webhook |
| `POST` | `/partner/events/test` | Send test webhook event |
| `GET` | `/partner/bonds` | List bonds (partner view) |
| `GET` | `/partner/bonds/{internal_id}` | Bond detail (partner view) |
| `GET` | `/partner/bonds/{internal_id}/analysis` | Full analysis (partner view) |
| `GET` | `/partner/usage` | API usage statistics |
| `POST` | `/partner/request` | Request a partner key |

---

## Billing

| Method | Path | Description |
|---|---|---|
| `GET` | `/billing/plans` | List subscription plans |
| `POST` | `/billing/create-payment` | Create a payment |
| `GET` | `/billing/subscription` | Get current subscription |
| `POST` | `/billing/webhook` | YooKassa webhook (IP-filtered) |

---

## Admin

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/login` | Admin login page |
| `POST` | `/admin/login` | Admin login |
| `GET` | `/admin/users` | List all users |
| `POST` | `/admin/users/{user_id}/toggle` | Activate/deactivate user |
| `POST` | `/admin/users/{user_id}/tier` | Change user subscription tier |

---

## WebSocket

The API supports WebSocket connections for real-time updates (e.g., alert push, live pricing).

Connect to: `ws://localhost:8000/ws` (or `wss://` in production)

---

## Aigenis Integration API

B2B-контракт поставки аналитики в отдельном namespace `/api/aigenis/v1`
(plan item 5.11). Полное OpenAPI-описание генерируется автоматически и доступно
на `/openapi.json`; здесь — краткая спецификация контракта.

### Auth

All endpoints require a Bearer token — SSO JWT от Aigenis IdP
(`Authorization: Bearer <jwt>`, `api/aigenis/security.py`). Валидируются
iss/aud/exp и подпись через JWKS; entitlement scopes:

| Scope | Purpose |
| --- | --- |
| `analytics:read` | списки и детальная аналитика бондов |
| `portfolio:read` | расчёт эффекта на портфель |
| `alerts:write` | создание алертов |

Fail-closed: в production отсутствующий/невалидный токен → `401`; нехватка
scope → `403`. В demo/staging без SSO-конфигурации — pass-through контекст.

### Endpoints

| Method | Path | Summary |
| --- | --- | --- |
| GET | `/api/aigenis/v1/bonds` | Список облигаций с Score (cursor pagination) |
| GET | `/api/aigenis/v1/bonds/{instrument_id}` | Детальная аналитика с объяснением Score |
| POST | `/api/aigenis/v1/portfolio-impact` | Оценка влияния на портфель |
| POST | `/api/aigenis/v1/alerts` | Создание алерта (идемпотентный) |

### Response headers (все ответы, plan item 5.13)

| Header | Meaning |
| --- | --- |
| `X-Request-Id` | correlation id (переиспользует входящий при наличии) |
| `X-Data-As-Of` | свежесть данных (`ISO 8601`) |
| `X-Model-Version` | версия скоринговой модели (`v1`) |
| `X-Data-Quality` | `ok` / `warning` / `critical` |

### Pagination (GET /bonds)

Keyset-cursor по `internal_id`:

```json
{
  "as_of": "2026-08-06T12:00:00+00:00",
  "data_status": "ok",
  "items": [],
  "next_cursor": "b-1024"
}
```

Параметры: `market` (`BCSE`|`MOEX`), `currency`, `limit` (1–100, default 50),
`cursor` (из `next_cursor`). Фильтры term/status принимаются на бэкенде и
применяются в W2 пилота.

### Error schema (все ошибки)

```json
{
  "error": "not_covered",
  "detail": null,
  "request_id": "6f4f...",
  "message": "Instrument X is not covered by the analytics engine."
}
```

Статусы:
- `401` — нет/невалидный SSO JWT (fail-closed)
- `403` — недостаточный scope
- `404` — инструмент не покрыт (`not_covered`), а не 500
- `422` — валидация тела/параметров (pydantic)

Rate limit: общие лимиты API (429 с `Retry-After`).

### Deprecation policy

Планируемые изменения контракта (поля, эндпоинты) объявляются заранее;
каждый эндпоинт в OpenAPI помежается тегом `deprecated` за N дней до
выключения. Версия контракта фиксируется в `X-Model-Version` / URL.

---

## Error Format

All errors return JSON:

```json
{
  "detail": "Human-readable error message",
  "code": "ERROR_CODE"
}
```

Common HTTP status codes:
- `401` — Unauthorized (missing/invalid token)
- `403` — Forbidden (insufficient permissions)
- `404` — Not found
- `422` — Validation error
- `429` — Rate limited
- `500` — Internal server error