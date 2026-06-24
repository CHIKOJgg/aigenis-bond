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

## Дорожная карта

- **V1** ✅ парсер, Postgres, история
- **V2** ✅ Score, Portfolio, сценарии, Telegram-бот
- **V3** ✅ ML-прогноз, рекомендации, auto-rebalance
- **V4** ✅ **Mini Fixed Income Desk** (Duration, Yield Curve, RV, Carry, Repo, Stress)

Итого **82 Python-файла**, 4 миграции Alembic, end-to-end smoke + 13 desk-тестов + V1-V3 test suite проходят.
