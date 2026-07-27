# Bonds Engine — One-Pager (для продажи кода)

**Коротко.** Готовый production-ready продукт для Fixed Income аналитики.
Парсер MOEX ISS + скоринг + ML + профессиональные Desk-инструменты +
Telegram bot + веб-интерфейс. Полный цикл: сбор данных → аналитика → продажа.

## Что внутри

### Data
- **MOEX ISS** — RUB корпоративные (TQCB) + USD/EUR евробонды (TQOB).
  Публичный источник, без логина.
- Автоматический сбор каждые 6 часов, догрузка истории до 5 лет.
- 100+ облигаций в базе.

### Core
- **Reward/Risk Score** 0-100 с буквенными тирами.
- **ML (scikit-learn)**: YTM регрессия + классификатор buy/hold/wait/avoid
  + объяснимые рекомендации + авто-ребаланс.
- **Fixed Income Desk**: Duration (Macaulay/Modified/DV01/convexity),
  Yield Curve (Nelson-Siegel), Relative Value (z-score), Carry, РЕПО,
  Stress Testing (7 сценариев).
- **Portfolio** — доходность, P&L, сценарии USD/BYN.

### Интерфейсы
- **Telegram bot** (aiogram 3) — все команды + Stars-платежи.
- **React SPA** (FastAPI backend) — дашборд, облигации, акции, портфель.
- **Partner API** — key management, webhooks (HMAC), read-only аналитика.
- **Embedded widget** — `/widget/embed.js` для встраивания на сторонние сайты.

### Инфраструктура
- Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, Redis 7
- Docker Compose (9 сервисов), Cloudflare Tunnel
- Prometheus + Grafana, Sentry, Loguru
- 102 теста, ruff, mypy, GitHub Actions CI
- **~44,000 строк кода** (Python 35k + TypeScript 9k)

## Что покупатель получает

- Весь Git-репозиторий с полной историей
- Docker-образы + docker-compose.yml
- Документацию по деплою (DEPLOYMENT.md)
- Все тесты и CI-пайплайн
- **Опционально**: разработчик на поддержку/доработку

## Варианты сделки

| Вариант | Цена | Входит |
|---------|------|--------|
| Код | **$15k** | Репозиторий + документация |
| Код + поддержка 3 мес | **$25k** | Код + 20ч/мес поддержки |
| Код + разработчик | **$30k+** | Код + full-time переход |

## Целевые покупатели

- Банки/брокеры РФ/РБ (нужен Fixed Income Desk для клиентов)
- Финтех-платформы (embedded-инвестиции)
- Агрегаторы котировок и финансовые медиа

**Контакты:** [ваш email / telegram]
