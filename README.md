# Aigenis Parser — Bond Fixed Income Assistant

V1: парсер Aigenis + Postgres + история + Docker.
V2: Reward/Risk Score, Portfolio Optimizer, сценарии USD/BYN, Telegram-бот, мониторинг.
V3: ML-прогноз, классификатор buy/hold/wait/avoid, рекомендации, auto-rebalance.
**V4: Mini Fixed Income Desk** — Duration, Yield Curve (Nelson-Siegel), Relative Value, Carry, Repo, Stress Testing.

## Структура

```
scraper/        # V1: парсер, pipeline, scheduler, health
scoring/        # V2: Reward/Risk Score
portfolio/      # V2-V3: оптимизатор, сценарии, позиции, auto-rebalance
monitoring/     # V2: детект изменений
notifications/  # V2: алерты + FX/металлы
forecast/       # V2: прогноз капитала
visualization/  # V2: matplotlib-графики
ml/             # V3: features, training, predict, recommendations
recommendations/# V3: explainable recommendations
desk/           # V4: duration, yield curve, RV, carry, repo, stress
telegram_bot/   # V2-V4: aiogram 3 бот
alembic/        # миграции 0001_init, 0002_v2, 0003_v3, 0004_v4
tests/          # pytest
```

## V4 — Mini Fixed Income Desk

### Модули

| Модуль | Файл | Что делает |
|---|---|---|
| **Duration** | `desk/duration.py` | Macaulay/Modified duration, convexity, DV01, key-rate durations |
| **Yield Curve** | `desk/yield_curve.py` | Nelson-Siegel fit (scipy), slope/curvature, интерполяция по тенору |
| **Relative Value** | `desk/relative_value.py` | Z-score спредов внутри валюты, rich/cheap сигналы |
| **Carry** | `desk/carry.py` | P&L от купона + rolldown по NS-кривой, breakeven |
| **Repo** | `desk/repo.py` | Сделки РЕПО: haircut по типу эмитента, начисление % |
| **Stress** | `desk/stress.py` | 7 пресет-сценариев (parallel, steepener, flattener, inversion, credit, fx) |

### CLI V4

```bash
python -m scraper desk-curve                 # Nelson-Siegel по всем валютам
python -m scraper desk-rv                    # rich/cheap сигналы (сохраняет в rv_signals)
python -m scraper desk-duration              # duration портфеля
python -m scraper desk-duration --bond OP-51 # duration облигации
python -m scraper desk-carry --funding 5.0   # carry с funding=5%
python -m scraper desk-repo --bond OP-51 --notional 1000 --tenor 30
python -m scraper desk-stress                # 7 пресетов (сохраняет в stress_runs)
python -m scraper desk-status                # последние сигналы
```

### Telegram-бот V4

```
/desk          — меню
/curve         — кривая доходности с NS-параметрами
/rv            — Relative Value (Z-score)
/duration [ID] — duration-отчёт (по облигации или портфелю)
/carry [fund]  — carry-ранжирование
/repo ID [N] [T] — сделка РЕПО
/stress        — все 7 пресетов
/desk_status   — сводка
```

### Scheduler

| Cron | Задача |
|---|---|
| `0 */6 * * *` | Парсинг + Score |
| `0 3 * * *` | История |
| `30 3 * * 0` | ML-train (еженедельно) |
| `0 4 * * *` | Auto-rebalance (ежедневно) |
| `30 4 * * *` | **desk-curve** (ежедневно) |
| `0 5 * * *` | **desk-rv** (ежедневно) |
| `0 5 * * 0` | **desk-stress** (еженедельно) |

### V4 — Тесты

```bash
pytest tests/test_desk.py
```

13 тестов покрывают: duration/convexity/DV01/key-rate, NS-фит, RV-сигналы, carry, repo (haircut по эмитенту), 7 стресс-сценариев.

### V4 — Финансовая валидация

Smoke-тест (20 USD-облигаций, modified dur ≈ 1.5):
```
parallel +100bp      P&L = -4.89%   ✓ (рост ставки → падение цены)
parallel -100bp      P&L = +2.89%   ✓
steepener            P&L = -5.57%   ✓ (длинные теряют больше)
credit shock +150bp  P&L = -6.83%   ✓ (кредитный риск дороже процентного)
fx shock -20%        P&L = -1.00%   ✓ (FX-удар на USD-портфель)
```

## V5 — Web + подписки (Telegram Stars)

Сайт (`frontend/`, React + Vite + Tailwind) повторяет бота 1:1: все страницы
(Dashboard, Bonds, Scores, Desk, Portfolio, Forecast, ML, Alerts) берут данные из
`/api/v1/*`. Pro/Enterprise-эндпоинты закрыты гейтингом по тарифу и возвращают
`402` для free-пользователей — фронтенд показывает экран подписки.

### Оплата — только Telegram Stars

Оплата принимается **исключительно** через Telegram Stars внутри бота. Кнопка
«Подписаться» на сайте ведёт в бота (`t.me/<bot>?start=subscribe`). Stripe-роутер
по умолчанию **не монтируется** (включается только если задан `STRIPE_SECRET_KEY`).

- `/subscribe` в боте — выбор тарифа, оплата XTR-инвойсом.
- Оплата **разовая** (aiogram 3.29 не поддерживает `subscription_period`): каждая
  покупка даёт окно `duration_days` (`users.subscription_expires_at`); продление —
  повторной оплатой. Тир автоматически истекает (учитывается и в боте, и на сайте).
- `successful_payment` **идемпотентен** по `telegram_payment_charge_id`
  (`users.last_charge_id`), refund через Stars отзывает подписку.

Настройки окружения:

```
TELEGRAM_BOT_USERNAME=your_bot      # для deep-link «Подписаться» на сайте
STARS_PRO=150                       # цена Pro в Stars (по умолчанию)
STARS_ENTERPRISE=500               # цена Enterprise в Stars
BOT_METRICS_PORT=9090              # /metrics и /health бота (0 = выключить)
RATE_LIMIT_BACKEND=redis           # общий rate-limit API через Redis (по умолчанию memory)
```

### Аналитический API (`/api/v1`)

| Эндпоинт | Тариф | Описание |
|---|---|---|
| `GET /api/v1/subscribe-info` | free | Тарифы Stars + deep-link на бота |
| `GET /api/v1/top`, `/bonds/{cur}` | free | Обзор рынка |
| `GET /api/v1/desk/{curve,rv,carry,stress}` | Pro | Desk-аналитика |
| `POST /api/v1/desk/repo` | Pro | РЕПО-калькулятор |
| `GET /api/v1/portfolio`, `/forecast`, `/scenarios` | Pro | Портфель/прогноз |
| `GET /api/v1/recommendations`, `/ml/*` | Pro | Рекомендации/ML |
| `GET /api/v1/alerts` | Pro | Алерты |

Гейтинг — `api.access_control.RequireFeature`; тир вычисляется с учётом срока
действия подписки.

### Наблюдаемость и качество данных

- Бот эмитит Prometheus-метрики (`bot_commands_total`, `bot_errors_total`,
  `bot_command_seconds`) через `MetricsMiddleware`; `/metrics` и `/health`
  поднимаются на `BOT_METRICS_PORT`.
- `monitoring.engine.detect_data_quality` создаёт алерты при `% облигаций без YTM`
  выше порога и «протухших» данных (старше 12 ч).

### Сборка сайта

```bash
cd frontend && npm install && npm run build   # -> frontend/dist
# API отдаёт dist, если задан FRONTEND_DIR
```

### CI

`.github/workflows/ci.yml`: `ruff check` (авторские модули) + `pytest`. Тесты
гермётичны — используют in-memory SQLite (см. `conftest.py`).

## Дорожная карта

- **V1** ✅ парсер, Postgres, история
- **V2** ✅ Score, Portfolio, сценарии, Telegram-бот
- **V3** ✅ ML-прогноз, рекомендации, auto-rebalance
- **V4** ✅ **Mini Fixed Income Desk** (Duration, Yield Curve, RV, Carry, Repo, Stress)
- **V5** ✅ **Web-платформа + подписки Telegram Stars**, аналитический API с гейтингом,
  метрики бота, алерты качества данных

Тесты: `pytest` — 62 проходят (desk-математика, гейтинг API, Stars-флоу с идемпотентностью
и истечением, качество данных, subscribe-info, рекомендации, ML-фичи, scoring).

## Production readiness

- **Fail-closed auth**: в `production` окружении (`AIGENIS_ENVIRONMENT=production`)
  отсутствие `JWT_SECRET_KEY` приводит к падению старта — токены нельзя подделать.
  Локально/в тестах используется небезопасный dev-секрет (предупреждение в логах).
- **Безопасные умолчания docker**: `ADMIN_PASSWORD` и `GRAFANA_ADMIN_PASSWORD`
  пусты по умолчанию (нужно задать явно), Prometheus/Grafana привязаны к
  `127.0.0.1` (не экспонируются наружу).
- **Публичный доступ**: опциональный Cloudflare Tunnel (`--profile tunnel`) — HTTPS
  без проброса портов; токен задаётся в `CLOUDFLARED_TUNNEL_TOKEN`.
- **Линт/типы**: backend — `ruff check .` чисто; frontend — `npm run lint` и
  `npm run build` (tsc + vite) проходят. CI (`.github/workflows/ci.yml`) гоняет
  `ruff` и `pytest`.
