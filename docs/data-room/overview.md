# Data Room — Bonds Engine

## Архитектура

```
MOEX ISS (публичный) → scraper/moex.py → PostgreSQL → FastAPI API → React SPA
                                                              → Telegram bot
                                                              → Partner API
                                                              → Widget (iframe)
```

- **Backend:** Python 3.13, FastAPI (async), SQLAlchemy 2.0, PostgreSQL 16, Redis 7
- **Frontend:** React 19, TypeScript 6, Vite 6, Tailwind CSS 4, Recharts
- **ML:** scikit-learn (YTM regression + classifier), NumPy, SciPy (Nelson-Siegel)
- **Infra:** Docker Compose (9 сервисов), nginx, Cloudflare Tunnel
- **Monitoring:** Prometheus + Grafana, Sentry, Loguru

## Кодовые метрики

| Категория | Значение |
|-----------|----------|
| Python строк кода | ~26,800 |
| TypeScript строк | ~8,700 |
| Тесты | 102 (pytest) |
| Linting | ruff, oxlint |
| Type checking | mypy (opt-in strict), tsc --strict |
| CI | GitHub Actions (lint, typecheck, test, build) |
| Миграции БД | 26 Alembic migrations |

## Security

- **Auth:** JWT (HS256, 30min), bcrypt, refresh tokens
- **Rate limiting:** nginx (100r/s) + app (60r/min) + per-key (120r/min)
- **CSP:** Content-Security-Policy, X-Frame-Options DENY
- **API keys:** SHA-256 hashed, one-time display
- **Webhooks:** HMAC-SHA256 signed payloads
- **SQL:** SQLAlchemy ORM (parameterised queries)
- **Payments:** YooKassa IP whitelist + double verification

## Deployment

- Docker Compose 🡒 `docker compose up -d`
- Cloudflare Tunnel для HTTPS без белого IP
- Makefile для всех операций (build, up, logs, backup)

## Модули

| Модуль | Описание |
|--------|----------|
| scraper/ | Парсер MOEX ISS (moex.py) + адаптер aigenis.by |
| api/ | FastAPI (REST + Server-Rendered SEO + Billing + Partner API) |
| frontend/ | React SPA + Widget + Landing Page |
| telegram_bot/ | aiogram 3 бот |
| desk/ | Fixed Income Desk (Duration, Curve, RV, Carry, Stress) |
| ml/ | ML-модели (YTM, классификатор) |
| scoring/ | Reward/Risk Score |
| portfolio/ | Портфельный менеджер |
