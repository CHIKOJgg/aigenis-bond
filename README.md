# Aigenis — AI-powered Bond & Stock Analytics Platform

V1: парсер облигаций + Postgres + история + Docker.
V2: Reward/Risk Score, Portfolio Optimizer, сценарии USD/BYN, Telegram-бот, мониторинг.
V3: ML-прогноз, классификатор buy/hold/wait/avoid, рекомендации, auto-rebalance.
V4: Mini Fixed Income Desk — Duration, Yield Curve (Nelson-Siegel), Relative Value, Carry, Repo, Stress Testing.
**V5: MOEX Stock Parser** — Акции MOEX (TQBR/TQOD/TQDE), OHLCV-история, секторальная аналитика, API.

## Deployment

Полное руководство по развёртыванию (Docker Compose, секреты, HTTPS, бот, мониторинг,
бэкапы, troubleshooting) — **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Структура

```
scraper/        # V1: парсер, pipeline, scheduler, health + V5: moex_stocks.py
scoring/        # V2: Reward/Risk Score
portfolio/      # V2-V3: оптимизатор, сценарии, позиции, auto-rebalance
monitoring/     # V2: детект изменений
notifications/  # V2: алерты + FX/металлы
forecast/       # V2: прогноз капитала
visualization/  # V2: matplotlib-графики
ml/             # V3: features, training, predict, recommendations
recommendations/# V3: explainable recommendations
desk/           # V4: duration, yield curve, RV, carry, repo, stress
api/            # V5: FastAPI REST API + stocks endpoints
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
python -m scraper alerts-check                # проверить пользовательские алерты и уведомить
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
/alerts        — мои алерты, срабатывания и рыночные события
/status        — мой тариф и сколько дней доступа осталось
```

Онбординг: на `/start` пользователю заводится аккаунт и включается 7-дневный
пробный Pro (об этом сразу сообщается баннером). `/status` (кнопка «👤 Мой тариф»)
показывает эффективный тариф и остаток дней. Пустые состояния сформулированы
для пользователя («данные загружаются»), без технических команд парсера.

Карточка облигации (🔍 Облигации → валюта → облигация) сразу показывает факты
(валюта, погашение, цена, доходность, купон) и рейтинг с вердиктом, а также кнопки:
`💡 Стоит купить?` (вердикт простыми словами), `💰 Доход` (купоны, Pro),
`🔔 Следить за ценой` (персональные ценовые/доходностные алерты в один тап, Pro),
`➕ В портфель` (добавить реальную позицию, Pro), `📈 ML-прогноз`,
`🔬 Для профи` (Duration/РЕПО в отдельном подменю), `⭐ В избранное`.

Портфель (💼 Портфель → 📌 Мои позиции, Pro) — учёт реальных облигаций: добавление
позиции из карточки с вводом суммы одним сообщением, удаление в один тап и сводка
купонного дохода (вложено, доход/год, доходность на вложенное, ближайшая выплата).
«📊 Модельный портфель» — рекомендуемое распределение (отдельно от реальных позиций).

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
| `0 8 * * *` | **alerts-check** (проверка пользовательских алертов) |

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

## V5 — Web + подписки (Telegram Stars и YooKassa)

Сайт (`frontend/`, React + Vite + Tailwind) повторяет бота 1:1: все страницы
(Dashboard, Bonds, Scores, Desk, Portfolio, Forecast, ML, Alerts) берут данные из
`/api/v1/*`. Pro/Enterprise-эндпоинты закрыты гейтингом по тарифу и возвращают
`402` для free-пользователей — фронтенд показывает экран подписки.

### Оплата — Telegram Stars (бот) и YooKassa (сайт)

Доступны **два** провайдера подписки, приводящих к одному источнику истины —
полю `users.subscription_tier`:

- **Telegram Stars (бот).** Кнопка «Подписаться» на сайте ведёт в бота
  (`t.me/<bot>?start=subscribe`). `/subscribe` в боте — выбор тарифа, оплата
  XTR-инвойсом. Оплата **разовая** (aiogram 3.29 не поддерживает
  `subscription_period`): каждая покупка даёт окно `duration_days`
  (`users.subscription_expires_at`); продление — повторной оплатой. Тир
  автоматически истекает (учитывается и в боте, и на сайте). `successful_payment`
  **идемпотентен** по `telegram_payment_charge_id` (`users.last_charge_id`),
  refund через Stars отзывает подписку.
- **YooKassa (сайт).** Карточные платежи через `api/billing`. Webhook от YooKassa
  **не подписан HMAC** — проверка производится повторным запросом объекта платежа
  к API YooKassa по `payment_id` (IP-адрес вебхука ограничен `YOOKASSA_WEBHOOK_IPS`).
  Сумма сверяется с тарифом, продление учитывает уже активную подписку.

Stripe-роутер по умолчанию **не монтируется** (включается только если задан
`STRIPE_SECRET_KEY`). Все переменные окружения — в `.env.example`.

Настройки окружения:

```
TELEGRAM_BOT_USERNAME=your_bot      # для deep-link «Подписаться» на сайте
STARS_PRO=150                       # цена Pro в Stars (по умолчанию)
STARS_ENTERPRISE=500               # цена Enterprise в Stars
YOOKASSA_SHOP_ID=...                # включает приём карт на сайте
YOOKASSA_SECRET_KEY=...
YOOKASSA_WEBHOOK_IPS=...            # CIDR/IP, откуда приходят вебхуки (безопасность)
TRUSTED_PROXY=1                     # доверять X-Forwarded-For за реверс-прокси
BOT_METRICS_PORT=9090              # /metrics и /health бота (0 = выключить)
RATE_LIMIT_BACKEND=redis           # общий rate-limit API через Redis (по умолчанию memory)
```

### Аналитический API (`/api/v1`)

| Эндпоинт | Тариф | Описание |
|---|---|---|
| `GET /api/v1/subscribe-info` | free | Тарифы (Stars + YooKassa) + deep-link на бота |
| `GET /api/v1/top`, `/bonds/{cur}` | free | Обзор рынка |
| `GET /api/v1/bond/{id}` | free* | Карточка облигации: факты + Score + тир (полный разбор — Pro-апселл) |
| `GET /api/v1/bond/{id}/analysis` | Pro | Полный разбор: объяснение Score «почему», вердикт, ML-прогноз, RV-сигнал |
| `GET /api/v1/bond/{id}/cashflow` | Pro | График купонов + возврат номинала при вложении суммы (даты и суммы выплат) |
| `GET /api/v1/portfolio/income` | Pro | Календарь купонного дохода: годовой доход, yield-on-cost, ближайшая выплата, разбивка по месяцам |
| `GET /api/v1/desk/{curve,rv,carry,stress}` | Pro | Desk-аналитика |
| `POST /api/v1/desk/repo` | Pro | РЕПО-калькулятор |
| `GET /api/v1/portfolio`, `/forecast`, `/scenarios` | Pro | Персональный портфель/прогноз (реальные позиции и настройки пользователя) |
| `GET/POST/DELETE /api/v1/positions` | Pro | Управление позициями пользователя (его портфель) |
| `GET /api/v1/portfolio/plan` | Pro | План ребалансировки по фактическим позициям |
| `POST /api/v1/allocate` | Pro | Подбор корзины под цель: сумма + срок + риск → конкретные позиции и проекция |
| `POST /api/v1/build_plan` | Pro | План ребалансировки по текущим/переданным позициям |
| `POST /api/v1/rebalance` | Pro | Применить ребалансировку к сохранённым позициям |
| `GET /api/v1/recommendations`, `/ml/*` | Pro | Рекомендации/ML |
| `GET /api/v1/alerts` | Pro | Системные алерты качества данных |
| `POST/GET /api/v1/alerts/rules`, `DELETE /api/v1/alerts/rules/{id}` | Pro | Пользовательские алерты (цена/YTM пробила порог) |
| `GET /api/v1/alerts/feed` | Pro | Лента сработавших пользовательских алертов |

Гейтинг — `api.access_control.RequireFeature`; тир вычисляется с учётом срока
действия подписки. `free*`: карточка `/bond/{id}` доступна всем, но блок
`analysis` («почему покупать/избегать») отдаётся только Pro — точка апселла.

### MOEX Stock Parser (V5)

Парсер акций MOEX — бесплатный публичный источник (MOEX ISS, без авторизации).
Данные обновляются каждые 30 минут во время торговой сессии (10:00–18:00 МСК, пн-пт).

**Доски:** TQBR (RUB), TQOD (USD), TQDE (EUR)

#### CLI

```bash
python -m scraper moex-stocks                     # сбор всех акций (TQBR + TQOD + TQDE)
python -m scraper moex-stocks --boards TQBR       # только основной режим
```

#### API (`/api/v1/stocks`)

| Эндпоинт | Тариф | Описание |
|---|---|---|
| `GET /api/v1/stocks` | free | Список акций с фильтрацией по доске/сектору |
| `GET /api/v1/stocks/stats` | free | Агрегированная статистика (всего, по секторам, по доскам) |
| `GET /api/v1/stocks/sectors` | free | Сводка по секторам (P/E, див. доходность, капитализация) |
| `GET /api/v1/stocks/{id}` | free | Детали акции |
| `GET /api/v1/stocks/{id}/history` | free | История торгов (OHLCV) |
| `GET /api/v1/stocks/board/{board}` | free | Акции по доске |
| `GET /api/v1/stocks/top/dividend` | Pro | Топ по дивидендной доходности |
| `GET /api/v1/stocks/top/cap` | Pro | Топ по капитализации |
| `GET /api/v1/stocks/search/{query}` | free | Поиск по названию/тикеру/ISIN |

#### Scheduler

```
*/30 10-18 * * 1-5  moex_stocks_30m    # каждые 30 мин во время торгов (пн-пт)
```

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
- **V5.1** ✅ **MOEX Stock Parser** — акции MOEX (TQBR/TQOD/TQDE), OHLCV-история,
  секторальная аналитика, REST API

Тесты: `pytest` — 102 проходят (desk-математика, гейтинг API, Stars-флоу с идемпотентностью, персональный портфель, алерты, allocate, карточка облигации с разбором Score, календарь купонного дохода, разбор «стоит ли купить», доход и персональные ценовые алерты в Telegram-боте, позиции портфеля из бота — добавление/удаление/сводка дохода, онбординг с пробным Pro и /status, ребалансировка по реальным позициям).

### Полировка UX бота (v5.1)
- Сообщения пользователю больше не содержат консольных команд (`python -m …`, «запустите парсер») — вместо них понятные подсказки («модели обновляются», «нажмите 🔄 Обновить данные»).
- «♻️ Ребалансировка» считается по реальным позициям из «📌 Мои позиции» (fallback на модельный портфель, если позиций нет).
- Пробный Pro стартует только когда данные загружены и показано меню — дни не сгорают на экране загрузки.
- `/overview` и `/desk` теперь открывают те же кнопочные подменю, что и пункты меню.
- Жаргон расшифрован (Sharpe/Sortino/VaR, параметры кривой Нельсона–Зигеля), «conf» → «уверенность %»; суммы в портфеле/прогнозе подписаны «BYN».
- «Watchlist» → «Избранное» везде; убраны дублирующиеся кнопки; пустые ответы дают подсказку, что делать дальше.

### Полировка UX бота (v5.2)
- Карточка «📈 ML-прогноз» приведена к тому же виду, что и `/predict` (уверенность %, «Прогноз доходности», без консольных подсказок) — устранена рассинхронизация двух путей к фиче.
- Отчёт Duration и блок РЕПО переведены на русский с расшифровками (DV01, haircut, срок), без английского сленга.
- Карточка «💰 Доход» и раздел «⚙️ Настройки» подписывают суммы валютой (BYN).
- Пресеты и стратегия в настройках — на русском («Консервативный» и т.п.); команда `/set` больше не навязывается (есть кнопки), ответы настроек на русском с валютой.

### Полировка UX бота (v5.3)
- Аналитика Desk доведена до русского: Relative Value — «отклонение Z» и «спред»; Carry — «доход от схлопывания кривой (п.п.)» и «прибыль» вместо rolldown/bp/P&L; Stress — «изменение стоимости портфеля»; Desk Status без сленга.
- Топ-10 и Сценарии подписаны («Score 0–100, выше — лучше»; сценарии — «изменение стоимости портфеля при шоке курса»).
- Экран подписки (Stars) перечисляет фичи по-русски (Duration (дюрация), Carry (кэрри), Relative Value).
- Главное меню очищено от дублей: разделы (Обзор/Рекомендации) — на главной, конкретные действия (Топ-10, Что купить) — внутри подменю.
- Пресеты алертов по доходности помечены «п.п.» (процентные пункты), чтобы не путать с относительным изменением.

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
