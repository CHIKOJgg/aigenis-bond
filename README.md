# Bonds Engine — Fixed Income Analytics Platform

## Коротко

**Bonds Engine** — движок аналитики облигаций, который превращает рыночные
данные в проверяемый инвестиционный контекст:

```text
market-data → нормализация → YTM/duration → Score → explainability
            → issuer risk → portfolio impact → API / UI / partner integration
```

Продукт рассчитан на брокерские приложения, инвестиционных советников,
портфельных менеджеров и B2B/white-label интеграции. Он не является торговым
терминалом и не заменяет compliance или инвестиционное решение.

## Что уже есть

### Данные и ingestion

- Live adapters для BCSE/MOEX и источник данных Aigenis.
- Сбор listing/detail, нормализация выпуска, ISIN, internal ID, валюты и рынка.
- Расчёт и хранение YTM, duration, цены, купона и срока погашения.
- История котировок и купонный календарь, когда их отдаёт источник.
- Scheduler, backfill, job runs, freshness и data-quality контроль.
- Instrument mapping для связывания внешних идентификаторов с внутренним выпуском.

### Scoring и риск

- Reward/Risk Score `0–100` и уровни `S/A/B/C/D`.
- Breakdown по доходности, валюте, duration, ликвидности, кредитному риску,
  инфляции, купону, волатильности и сравнению с аналогами.
- Explainability: сильные/слабые стороны, verdict и понятное объяснение факторов.
- Engine-derived issuer risk на основе классификации эмитента, credit component
  и статуса выпуска.
- Distressed marker для бумаг с признаками проблемного долга.
- Диверсификация рекомендаций по эмитентам.

Issuer risk — внутренний показатель движка, а не внешний кредитный рейтинг.
Для сравнений типа «эмитент A надёжнее эмитента B» нужны подтверждённые
финансовые показатели или рейтинговые данные.

### Fixed Income Desk

- YTM и cash-flow расчёты.
- Macaulay/modified duration, convexity, DV01/KRD.
- Nelson-Siegel yield curve.
- Relative Value: rich/cheap и spreads.
- Carry, repo и funding scenarios.
- Stress testing по сценариям изменения ставок, цены и доходности.

### Портфели

- Позиции, транзакции и FIFO P&L.
- Доход и денежные потоки.
- Allocation и portfolio impact.
- Оптимизация с YTM, Sharpe, Sortino, Calmar, VaR и ограничениями.
- Ребалансировка.
- Backtest и сценарный анализ.

### ML и forecast

- Feature engineering по инструментам и временным рядам.
- YTM regression и классификация сигналов.
- Walk-forward validation без look-ahead leakage.
- Monte Carlo forecast с p5/p25/p50/p75/p95 и CVaR.
- Registry и версии моделей.

### Интерфейс

React SPA содержит экраны:

- Dashboard;
- Bonds и bond detail;
- Stocks;
- Scores и Recommendations;
- Company/issuer pages;
- Portfolio и Portfolio Pro;
- Desk;
- Forecast;
- Alerts;
- Calculator;
- News и AI chat;
- Document Analysis;
- Account и Subscribe;
- live demo и embeddable widget.

## Live Demo для Aigenis

```text
Торги → Аналитика → Score/YTM chart → Bond detail
      → issuer risk → Portfolio Impact → Купить
```

Запуск standalone demo:

```bash
docker compose up -d postgres redis parser api
docker compose -f docker-compose.demo.yml up -d --build
```

Открыть: `http://localhost:8080/demo`

В demo доступны:

- реальные live BCSE/MOEX данные с timestamp;
- поиск по названию, эмитенту, ISIN и internal ID;
- фильтры рынка, валюты, срока, статуса и ликвидности;
- график `Score ↔ YTM` по live-универсу;
- карточка с breakdown и explainability;
- issuer risk;
- before/after график Portfolio Impact;
- расчёт позиции в процентах, BYN или штуках;
- подготовка order context через кнопку `Купить`.

Demo read-only: кнопка `Купить` не отправляет заявку и не вызывает write API.
Она показывает, какие параметры будут переданы в торговый ticket Aigenis:
`internal_id`, market, currency и размер позиции.

## Архитектура

```text
BCSE/MOEX/Aigenis source
          ↓
scraper + scheduler + PostgreSQL
          ↓
scoring / desk / ML / forecast / portfolio / recommendations
          ↓
FastAPI REST API + Aigenis integration API + demo API
          ↓
React SPA / nginx / widget / Telegram bot / partner API
```

Сервисы Docker Compose:

- PostgreSQL 16 — основная БД, история и результаты расчётов;
- Redis 7 — cache, rate limiting и task coordination;
- parser — ingestion, scheduler, scoring, backfill и ML jobs;
- API — FastAPI, auth, analytics, portfolio, billing, partner и demo routes;
- frontend — React/Vite и nginx;
- bot — Telegram interactions, subscriptions and alerts;
- Prometheus/Grafana — metrics and dashboards;
- Sentry/notifications — optional error and delivery integrations.

## Структура репозитория

```text
api/              FastAPI routers, services, auth, billing, partner API
scraper/          Providers, parsers, scheduler, ORM, repositories
scoring/          Reward/Risk engine and explainability
desk/             Fixed Income calculations
portfolio/        Positions, P&L, optimizer, rebalance, backtest
ml/               Features, training, registry and predictions
forecast/         Monte Carlo and CVaR
recommendations/  Explainable recommendations
frontend/         React SPA, demo, widget and Playwright tests
telegram_bot/     Telegram bot and subscriptions
alembic/          Database migrations
monitoring/       Metrics and change detection
docs/             Application, operations and Aigenis sales documentation
tests/            Python test suite
```

## API namespaces

- `/api/v1/*` — application analytics and portfolio API;
- `/api/v1/demo/*` — protected read-only live demo API;
- `/api/aigenis/v1/*` — B2B integration contract for Aigenis;
- `/api/v1/partner/*` — partner keys, usage, webhooks and partner analytics;
- `/widget/*` — public widget endpoints.

Demo API routes:

- `GET /api/v1/demo/market-data?market=bcse|moex`;
- `GET /api/v1/demo/search?q=...`;
- `GET /api/v1/demo/bond/{internal_id}`.

## Технологии

- Python 3.13, FastAPI, SQLAlchemy 2, asyncpg, Alembic;
- PostgreSQL 16, Redis 7;
- NumPy, pandas, SciPy, scikit-learn;
- React 19, TypeScript, Vite, React Router;
- Recharts/Lucide/Tailwind-compatible UI layer;
- Playwright, Vitest, Testing Library;
- Docker Compose, nginx, Prometheus, Grafana.

## Проверка

Frontend-команды:

```bash
cd frontend
npm ci
npm run lint
npm run test
npm run build
npm run test:e2e
npm run test:e2e:visual
```

Runtime smoke:

```bash
curl -f http://localhost:8080/health
curl -f "http://localhost:8080/api/v1/demo/market-data?market=bcse&limit=5"
docker compose ps
docker compose -f docker-compose.demo.yml ps
```

## Ограничения и честный статус

- Live demo — proof-of-value, а не готовая интеграция в aigenis invest.
- Production-поставка требует официального data contract, instrument mapping,
  SSO, deployment и compliance acceptance.
- Demo не выставляет реальные заявки и не содержит клиентских данных.
- Issuer risk не является рейтинговым агентством или гарантией дефолта.
- Forecast/ML и Score не гарантируют доходность.
- Права на коммерческое хранение и распространение данных нужно согласовать
  отдельно для каждого источника.

## Документация

- [Документация проекта](docs/README.md)
- [Архитектура](docs/app/architecture.md)
- [API Reference](docs/app/API.md)
- [Scoring Methodology](docs/app/METHODOLOGY.md)
- [Deployment](docs/app/DEPLOYMENT.md)
- [Security](docs/app/SECURITY.md)
- [Aigenis Live Demo Runbook](docs/aigenis/demo-runbook.md)
- [Aigenis Pitch Script](docs/aigenis/pitch-script.md)
- [Aigenis One-Pager](docs/aigenis/one-pager.md)
- [Negotiation Guide](docs/aigenis/negotiation-guide.md)
- [Technical Due Diligence](docs/aigenis/technical-due-diligence.md)

## Лицензия

Proprietary — AIGENIS INVEST.
