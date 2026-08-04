# Bonds Engine - Technical Due Diligence Q&A

Ответы на технические вопросы, которые задаст CTO/технический директор покупателя
при проверке кода и архитектуры.

---

## Архитектура

### Как устроен data pipeline?
1. **APScheduler** запускает джобы каждые 4-6 часов
2. **MOEX ISS API** - публичный REST, пагинация, rate limiting с backoff
3. **Парсеры** разбирают ответы в Pydantic-модели
4. **Валидация** данных перед записью
5. **Async SQLAlchemy** upsert в PostgreSQL
6. **Fallback source** - авто-переключение при недоступности основного источника
7. **History backfill** - 5 лет истории цен/YTM

Схема: MOEX ISS -> Parser -> Validator -> ORM -> PostgreSQL
                                     |
                              APScheduler (cron)

### Как масштабируется?
- Stateless API (FastAPI) - горизонтальное масштабирование
- Redis для кэша и rate limiting
- PostgreSQL с индексами по internal_id, currency, maturity_date
- Nginx reverse proxy с gzip и кэшированием статики
- Docker Compose для оркестрации (можно мигрировать на K8s)

### Почему не микросервисы?
Продукт построен как модульный монолит с чёткими границами:
- `scraper/` - сбор данных
- `scoring/` - расчёт скоринга
- `desk/` - аналитика
- `ml/` - машинное обучение
- `portfolio/` - управление портфелем
- `api/` - REST API
- `telegram_bot/` - бот

Каждый модуль - независимый Python-пакет со своими тестами. При необходимости
выносится в отдельный сервис без переписывания логики.

---

## База данных

### Схема БД
20+ таблиц:
- `bonds` - основная таблица облигаций
- `bond_history` - исторические данные (5 лет)
- `bond_scores` - предрассчитанные скоринги
- `stocks` / `stock_history` - акции MOEX
- `fx_rates` - курсы валют
- `users` / `user_preferences` / `subscriptions`
- `alerts` / `alert_deliveries`
- `portfolios` / `transactions` / `positions`
- `partner_api_keys` / `webhook_subscriptions`
- `referrals` / `billing_events`

### Миграции
24 миграции Alembic. Автоматически применяются при старте контейнера
(docker-entrypoint.sh). Миграции протестированы на forward/backward.

### Индексы
- `internal_id` (primary lookup)
- `currency` (фильтрация)
- `maturity_date` (сортировка)
- `issuer` (группировка)
- `status` (фильтрация активных)
- `yield_to_maturity` (сортировка по доходности)
- Составной индекс (currency, status, maturity_date)

---

## Безопасность

### Как работает аутентификация?
- JWT HS256, 30 минут expiry
- Bcrypt хэширование паролей
- Refresh tokens с ротацией
- Google OAuth (опционально)
- Fail-closed: при ошибке валидации - отказ в доступе

### Защита от атак
- **Rate limiting**: Redis/in-memory, тир-зависимые лимиты
  - Free: 60 req/min
  - Pro: 120 req/min
  - Enterprise: 300 req/min
  - API Pro: 600 req/min
  - White-label: 1200 req/min
- **SSRF**: проверка IP (пиннинг + IPv6)
- **Webhook HMAC**: все внешние webhook-подписки подписаны
- **YooKassa refund guard**: проверка IP источника, перепроверка API, полная сумма
- **Telegram Stars**: идемпотентность по telegram_payment_charge_id
- **CSP / X-Frame-Options / X-Content-Type-Options**: security headers
- **CORS**: whitelist доменов

### Где хранятся секреты?
.env файл (не в репозитории). Генерация через `scripts/generate_secrets.py`
(криптографически стойкие ключи).

---

## Тестирование

### Какие тесты есть?
- **Unit**: чистая логика (скоринг, desk-расчёты, ML-метрики)
- **Integration**: API эндпоинты с тестовой БД (SQLite in-memory)
- **Security**: auth flow, rate limiting headers, admin access control
- **Billing**: webhook processing, refund validation, payment idempotency
- **Bot**: gating logic, navigation, Stars payment flow
- **Load**: Locust нагрузочные тесты (директория tests/load/)

### Как запустить тесты?
```bash
pytest tests/ -v
# или конкретный модуль:
pytest tests/test_scoring.py tests/test_desk.py -v
```

### Coverage
~80%+ критического пути (скоринг, биллинг, auth, API). Деск-модули покрыты
smoke-тестами математической корректности.

---

## ML

### Как обучаются модели?
1. **Feature engineering**: 30+ признаков из bond_history (YTM, momentum, spread, duration)
2. **Walk-forward CV**: окна по времени, нет look-ahead leakage
3. **GradientBoostingRegressor**: прогноз YTM
4. **GradientBoostingClassifier**: buy/hold/wait/avoid
5. **Артефакты**: сохраняются с версией и метаданными (ml/artifacts/)

### Как часто переобучать?
Рекомендуется раз в 1-2 недели при активном сборе данных. Автоматический
пайплайн в `ml/engine.py`.

### Качество моделей?
- Регрессия YTM: зависит от рынка, типично R^2 0.6-0.8
- Классификация: accuracy на тестовых окнах валидации

Модели не дают гарантий, но дают статистически обоснованный сигнал.

---

## Деплой

### Что нужно для запуска?
- Сервер с Docker + Docker Compose
- 2+ CPU, 4+ GB RAM, 20+ GB диск
- Внешний IP или Cloudflare Tunnel
- Доменное имя (опционально для production)

### Команда для деплоя
```bash
cp .env.example .env
# заполнить SECRET_KEY, DB_PASSWORD, YOOKASSA_SHOP_ID и т.д.
docker compose up -d
```

Поднимается 9 сервисов: api, bot, scraper, postgres, redis, nginx, prometheus, grafana, cloudflared.

### Как обновлять?
```bash
git pull
docker compose build
docker compose up -d
```
Миграции применяются автоматически при старте.

---

## Мониторинг

### Что мониторится?
- **Prometheus**: метрики API (latency, errors, requests), бота (commands, errors)
- **Grafana**: дашборды (порт 3001)
- **Sentry**: исключения и ошибки
- **Loguru**: структурированные JSON-логи с ротацией
- **Health checks**: /health для каждого сервиса

### Алерты
- Падение сервиса (Docker healthcheck)
- Ошибки сбора данных
- Аномалии в данных
- Ошибки биллинга (критично)

---

## Производительность

### Нагрузочные характеристики
- API: 200+ RPS на medium инстансе (без ML-инференса)
- Бот: 50+ одновременных пользователей
- Сбор данных: полный цикл MOEX ISS ~30-60 секунд (1500+ бумаг)
- Скоринг: пересчёт всех облигаций ~5 секунд
- ML inference: ~1 секунда на батч из 100 облигаций

### Узкие места
- Внешние API (rate limits MOEX ISS)
- ML-обучение (CPU-intensive, рекомендуется запускать офлайн)
- PostgreSQL при >100k записей в bond_history (решается партиционированием)

---

## Зависимости

### Внешние сервисы
- MOEX ISS API (публичный, бесплатный)
- YooKassa API (для приёма платежей)
- Telegram Bot API (для бота)
- OpenRouter / OpenAI (для AI-чата, опционально)
- Cloudflare Tunnel (опционально, для доступа без белого IP)
- Sentry (опционально, для error tracking)

### Зависимости Python (ключевые)
- fastapi, uvicorn, sqlalchemy[asyncio], alembic, pydantic
- aiogram, apscheduler, httpx
- scikit-learn, numpy, scipy
- loguru, prometheus_client, sentry-sdk

### Зависимости JS
- react, react-dom, react-router-dom
- tailwindcss, recharts
- vite, typescript, vite-plugin-pwa
