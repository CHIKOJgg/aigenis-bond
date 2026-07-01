# Deployment Guide — Aigenis Parser v2

## Содержание

1. [Требования](#1-требования)
2. [Быстрый старт (Docker)](#2-быстрый-старт-docker)
3. [Ручная установка](#3-ручная-установка)
4. [Конфигурация](#4-конфигурация)
5. [База данных и миграции](#5-база-данных-и-миграции)
6. [Запуск компонентов](#6-запуск-компонентов)
7. [Production-рекомендации](#7-production-рекомендации)
8. [Мониторинг и алерты](#8-мониторинг-и-алерты)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Требования

### Минимальные системные требования

| Ресурс | Минимум | Рекомендуется |
|--------|---------|---------------|
| CPU | 2 ядра | 4 ядра |
| RAM | 2 GB | 4 GB |
| Диск | 10 GB | 20 GB (SSD) |

### Зависимости

- **OS**: Linux (Ubuntu 22.04+/Debian 12+) или Windows Server 2019+
- **Docker** 24+ (если используете контейнеризацию)
- **Python** 3.13+
- **PostgreSQL** 16+
- **Redis** 7+
- **Playwright** (устанавливается автоматически с браузером Chromium)

### Сеть

- Доступ к `https://aigenis.by` (порт 443)
- Для Telegram-бота: доступ к API Telegram (`api.telegram.org`)
- Открытые порты: `5432` (PostgreSQL, внутренний), `6379` (Redis, внутренний)

---

## 2. Быстрый старт (Docker)

Самый простой способ развернуть всю систему.

### 2.1. Клонирование и настройка

```bash
git clone <repo-url> aigenis-parser
cd aigenis-parser
```

### 2.2. Переменные окружения

```bash
cp .env.example .env
# Отредактируйте .env под ваш проект:
nano .env
```

Минимально необходимые переменные:

```env
# Обязательно изменить:
DATABASE_URL=postgresql+asyncpg://aigenis:aigenis@postgres:5432/aigenis

# Для Telegram-бота (опционально, но рекомендовано):
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALERT_CHAT_ID=your_chat_id_here
```

### 2.3. Запуск

```bash
# Запуск всех сервисов (парсер + БД + Redis)
docker compose up -d

# Запуск с Telegram-ботом
docker compose --profile bot up -d

# Инициализация схемы БД (первый запуск)
docker compose run --rm alembic
```

### 2.4. Проверка

```bash
# Проверить работу парсера
docker compose exec parser python -m scraper health

# Проверить, что данные собираются (однократный прогон)
docker compose exec parser python -m scraper once

# Проверить API (если настроен)
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## 3. Ручная установка

Если вы не используете Docker.

### 3.1. Установка Python 3.13

**Ubuntu/Debian:**

```bash
sudo apt update && sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install -y python3.13 python3.13-dev python3.13-venv
```

### 3.2. Установка PostgreSQL 16

```bash
sudo apt update && sudo apt install -y postgresql-16 postgresql-client-16
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Создание пользователя и базы
sudo -u postgres psql -c "CREATE USER aigenis WITH PASSWORD 'aigenis';"
sudo -u postgres psql -c "CREATE DATABASE aigenis OWNER aigenis;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE aigenis TO aigenis;"
```

### 3.3. Установка Redis

```bash
sudo apt update && sudo apt install -y redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### 3.4. Установка проекта

```bash
# Виртуальное окружение
python3.13 -m venv .venv
source .venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -e ".[dev]"

# Установка браузера Playwright
playwright install chromium
```

### 3.5. Настройка окружения

```bash
cp .env.example .env
nano .env
```

Обязательно укажите:

```env
DATABASE_URL=postgresql+asyncpg://aigenis:aigenis@localhost:5432/aigenis
DATABASE_URL_SYNC=postgresql://aigenis:aigenis@localhost:5432/aigenis
REDIS_URL=redis://localhost:6379/0
AIGENIS_HEADLESS=true
```

### 3.6. Миграции

```bash
alembic upgrade head
```

---

## 4. Конфигурация

### 4.1. Структура конфигурации

Проект использует **pydantic-settings** с иерархической конфигурацией:

```
AppSettings
├── aigenis (scraper)     → префикс AIGENIS_*
├── database (DB)          → префикс DB_* или DATABASE_URL
├── redis                  → префикс REDIS_* или REDIS_URL
└── telegram (бот)         → префикс TELEGRAM_*
```

### 4.2. Ключевые переменные

#### Scraper (`AIGENIS_*`)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `AIGENIS_BASE_URL` | `https://aigenis.by` | Базовый URL источника данных |
| `AIGENIS_DATA_API_URL` | `None` | Внутренний JSON API (если есть) |
| `AIGENIS_HEADLESS` | `true` | Режим браузера без GUI |
| `AIGENIS_DELAY_BETWEEN_REQUESTS` | `2.0` | Задержка между запросами (сек) |
| `AIGENIS_MAX_CONCURRENCY` | `2` | Макс. параллельных страниц |
| `AIGENIS_MAX_RETRIES` | `3` | Количество retry при ошибках |
| `AIGENIS_TIMEOUT` | `30` | Таймаут запроса (сек) |

#### База данных (`DATABASE_URL`, `DB_*`)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `DATABASE_URL` | — | Async DSN PostgreSQL |
| `DATABASE_URL_SYNC` | — | Sync DSN для инструментов |
| `DB_POOL_SIZE` | `10` | Размер пула соединений |
| `DB_POOL_OVERFLOW` | `20` | Доп. соединения сверх пула |
| `DB_POOL_RECYCLE` | `3600` | Пересоздание соединений (сек) |
| `DB_SLOW_QUERY_THRESHOLD_S` | `0.1` | Порог медленного запроса |

#### Redis (`REDIS_URL`)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `REDIS_URL` | `redis://localhost:6379/0` | URL подключения |
| `REDIS_MAX_CONNECTIONS` | `20` | Макс. соединений в пуле |
| `REDIS_SOCKET_TIMEOUT` | `5.0` | Таймаут сокета (сек) |

#### Telegram (`TELEGRAM_*`)

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `TELEGRAM_BOT_TOKEN` | — | Токен бота (обязательно) |
| `TELEGRAM_ADMIN_IDS` | — | ID админов через запятую |
| `WEBHOOK_URL` | — | URL вебхука (вместо polling) |

### 4.3. Пример `.env` для прода

```env
# --- Scraper ---
AIGENIS_BASE_URL=https://aigenis.by
AIGENIS_HEADLESS=true
AIGENIS_USE_STEALTH=true
AIGENIS_DELAY_BETWEEN_REQUESTS=3.0
AIGENIS_MAX_CONCURRENCY=3
AIGENIS_MAX_RETRIES=5
AIGENIS_TIMEOUT=60
AIGENIS_HISTORY_BACKFILL_DAYS=1825

# --- Logging ---
AIGENIS_LOG_LEVEL=INFO
AIGENIS_LOG_JSON=true
AIGENIS_LOG_FILE=/var/log/aigenis/scraper.log
AIGENIS_LOG_ROTATION=500 MB
AIGENIS_LOG_RETENTION=30 days

# --- Sentry (опционально) ---
SENTRY_DSN=https://key@sentry.io/project
AIGENIS_ENVIRONMENT=production

# --- Database ---
DATABASE_URL=postgresql+asyncpg://aigenis:strong_password@db-host:5432/aigenis
DATABASE_URL_SYNC=postgresql://aigenis:strong_password@db-host:5432/aigenis
DB_POOL_SIZE=20
DB_POOL_OVERFLOW=40
DB_POOL_RECYCLE=1800
DB_SLOW_QUERY_THRESHOLD_S=0.5

# --- Redis ---
REDIS_URL=redis://redis-host:6379/0
REDIS_MAX_CONNECTIONS=50

# --- Telegram ---
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_ALERT_CHAT_ID=-1001234567890
TELEGRAM_ADMIN_IDS=123456789,987654321
```

---

## 5. База данных и миграции

### 5.1. Структура

Проект использует **Alembic** для управления схемой. Файлы миграций: `alembic/versions/`.

### 5.2. Выполнение миграций

```bash
# Все неприменённые миграции
alembic upgrade head

# Откат на одну миграцию
alembic downgrade -1

# Просмотр статуса
alembic current
alembic history
```

### 5.3. Создание новой миграции

```bash
# После изменения ORM-моделей в scraper/orm.py:
alembic revision --autogenerate -m "описание_изменений"
alembic upgrade head
```

### 5.4. Резервное копирование

```bash
# Ежедневный бэкап PostgreSQL
pg_dump -U aigenis -h localhost aigenis > backup_$(date +%Y%m%d).sql

# Восстановление
psql -U aigenis -h localhost aigenis < backup_20260101.sql
```

---

## 6. Запуск компонентов

### 6.1. Парсер (сбор данных)

```bash
# Однократный сбор всех данных
python -m scraper once

# Сбор по конкретным валютам
python -m scraper once --currency USD,BYN

# Дозагрузка истории
python -m scraper backfill --days 365

# Запуск планировщика (cron)
python -m scraper run
```

Планировщик выполняет:

| Задача | Расписание | Описание |
|--------|-----------|----------|
| scrape_all_6h | Каждые 6 часов | Полный сбор листинга + деталей |
| scrape_history_daily | Ежедневно в 3:00 | Дозагрузка истории |
| ml_train_weekly | Воскресенье в 3:30 | Обучение ML-моделей |
| auto_rebalance_daily | Ежедневно в 4:00 | Проверка дрифта портфеля |
| desk_curve_daily | Ежедневно в 4:30 | Кривая доходности |
| desk_rv_daily | Ежедневно в 5:00 | Relative Value сигналы |
| desk_stress_weekly | Воскресенье в 5:00 | Стресс-тесты |

### 6.2. Telegram-бот

```bash
# Polling режим (по умолчанию)
python -m telegram_bot.bot

# Webhook режим
WEBHOOK_URL=https://your-domain.com \
WEBHOOK_PATH=/webhook \
WEBHOOK_PORT=8443 \
python -m telegram_bot.bot
```

### 6.3. REST API

```bash
# Разработка
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn -k uvicorn.workers.UvicornWorker api.main:app \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/aigenis/api.access.log \
    --error-logfile /var/log/aigenis/api.error.log
```

### 6.4. Desk-команды (аналитика)

```bash
# Кривая доходности (Nelson-Siegel)
python -m scraper desk-curve

# Relative Value
python -m scraper desk-rv

# Duration-отчёт
python -m scraper desk-duration --bond OP-51

# Carry-ранжирование
python -m scraper desk-carry --funding 5.0

# Сделка РЕПО
python -m scraper desk-repo --bond OP-51 --notional 10000 --tenor 30

# Стресс-тесты
python -m scraper desk-stress

# Health-check
python -m scraper health
```

---

## 7. Production-рекомендации

### 7.1. Безопасность

- **Всегда меняйте пароли** по умолчанию (PostgreSQL, Redis)
- Используйте `.env` с `chmod 600` — не храните секреты в репозитории
- Настройте **firewall**: PostgreSQL (5432) и Redis (6379) не должны быть доступны извне
- Используйте **HTTPS** для API и вебхуков Telegram-бота
- Запускайте контейнеры от **non-root** пользователя (уже настроено в Dockerfile)
- Регулярно обновляйте зависимости: `pip audit` или `pip-audit`

### 7.2. Надёжность

- Настройте **мониторинг PostgreSQL**: `pg_stat_activity`, `pg_stat_statements`
- Включите **Redis persistence** (RDB/AOF) — уже настроено в `docker-compose.yml`
- Используйте **systemd** для автозапуска:

```ini
# /etc/systemd/system/aigenis-parser.service
[Unit]
Description=Aigenis Parser
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/aigenis-parser
EnvironmentFile=/opt/aigenis-parser/.env
ExecStart=/opt/aigenis-parser/.venv/bin/python -m scraper run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 7.3. Производительность

- Настройте `DB_POOL_SIZE` под нагрузку (формула: `workers * 2`)
- Используйте **pgBouncer** для пулинга соединений к PostgreSQL
- Настройте **Redis maxmemory** политику: `allkeys-lru`
- Для Playwright: ограничьте `AIGENIS_MAX_CONCURRENCY` до 2-3, чтобы не перегружать CPU
- Включите **логирование медленных запросов** через `DB_SLOW_QUERY_THRESHOLD_S`

### 7.4. Логирование

```bash
# Настройка logrotate:
# /etc/logrotate.d/aigenis
/var/log/aigenis/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

### 7.5. Обновление

```bash
# С Docker:
git pull
docker compose build --no-cache parser
docker compose up -d

# Без Docker:
git pull
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
alembic upgrade head
sudo systemctl restart aigenis-parser
```

---

## 8. Мониторинг и алерты

### 8.1. Встроенный health-check

```bash
python -m scraper health
# {"status": "ok", "bonds_total": 150, "history_total": 45000, "last_fetched_at": "2026-01-15T10:30:00"}
```

### 8.2. API endpoints

```bash
# Health
curl http://localhost:8000/health
# {"status": "ok", "db": "ok", "uptime_seconds": 86400}

# Readiness (для k8s)
curl http://localhost:8000/ready

# Prometheus-совместимые метрики (если настроены)
curl http://localhost:8000/metrics
```

### 8.3. Telegram-алерты

Система автоматически отправляет уведомления о:

- Изменении статуса облигации (погашена/снята)
- Наступлении даты оферты
- Высоком Score (>90 баллов)
- Значительных изменениях курсов валют (>0.5%)
- Значительных изменениях цен металлов (>0.5%)

Настройте `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ALERT_CHAT_ID` в `.env`.

### 8.4. Мониторинг через Prometheus (+ Grafana)

Добавьте в `docker-compose.yml`:

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
```

Создайте `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: aigenis
    static_configs:
      - targets: ['parser:8000']
```

### 8.5. Sentry (опционально)

Для отслеживания ошибок в production настройте `SENTRY_DSN`:

```env
SENTRY_DSN=https://your-key@sentry.io/project-id
AIGENIS_ENVIRONMENT=production
```

---

## 9. Troubleshooting

### 9.1. Парсер не стартует

**Проблема**: `RuntimeError: DATABASE_URL is not set`

**Решение**: Убедитесь, что `.env` существует и содержит `DATABASE_URL`.

```bash
cat .env | grep DATABASE_URL
```

---

**Проблема**: `playwright._impl._errors.Error: Browser closed`

**Решение**: Playwright требует ресурсы. Увеличьте память или уменьшите `AIGENIS_MAX_CONCURRENCY`.

---

**Проблема**: `FatalError: captcha detected`

**Решение**: Включите `AIGENIS_USE_STEALTH=true` или смените User-Agent. Слишком частые запросы могут вызвать блокировку — увеличьте `AIGENIS_DELAY_BETWEEN_REQUESTS`.

---

### 9.2. Telegram-бот не отвечает

**Проблема**: `FATAL: missing env vars: TELEGRAM_BOT_TOKEN`

**Решение**: Проверьте `.env`:

```bash
grep TELEGRAM_BOT_TOKEN .env
```

---

**Проблема**: Бот запущен, но не отвечает на команды

**Решение**: Проверьте, не запущен ли второй экземпляр. Используйте `webhook` вместо `polling` или наоборот. Telegram позволяет только один метод одновременно.

---

### 9.3. Медленные запросы к API

**Проблема**: API отвечает >1 секунды

**Решение**:
1. Проверьте `DB_SLOW_QUERY_THRESHOLD_S` — в логах будут видны медленные запросы
2. Увеличьте `DB_POOL_SIZE`
3. Добавьте индексы на часто запрашиваемые колонки

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_bonds_currency_status ON bonds(currency, status);
```

---

### 9.4. Docker: контейнер не стартует

**Проблема**: `Error response from daemon: ... no matching manifest for windows/amd64`

**Решение**: Образ Playwright не поддерживает Windows. Используйте WSL2 или Linux.

---

**Проблема**: `postgres` контейнер не готов, `parser` падает

**Решение**: Docker Compose настроен с `depends_on: condition: service_healthy`. Подождите 30-60 секунд при первом запуске. Проверьте:

```bash
docker compose logs postgres
docker compose logs alembic
```

---

### 9.5. Alembic миграции

**Проблема**: `FAILED: Target database is not up to date.`

**Решение**:

```bash
alembic upgrade head
```

**Проблема**: `FAILED: Can't locate revision identified by 'xxx'`

**Решение**: Исправьте ветку миграций:

```bash
alembic history
alembic current
alembic upgrade +1
```

---

### 9.6. Проверка целостности

```bash
# Быстрая проверка данных
python -m scraper health

# Полная верификация (mock + sqlite + live)
python verify_aigenis.py

# Сгенерировать отчёт verify_report.json
```

---

## Приложение A: systemd unit для Gunicorn

```ini
[Unit]
Description=Aigenis API server
After=network.target postgresql.service

[Service]
User=appuser
WorkingDirectory=/opt/aigenis-parser
EnvironmentFile=/opt/aigenis-parser/.env
ExecStart=/opt/aigenis-parser/.venv/bin/gunicorn \
    -k uvicorn.workers.UvicornWorker \
    api.main:app \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/aigenis/api.access.log \
    --error-logfile /var/log/aigenis/api.error.log
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Приложение B: Nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name aigenis-api.example.com;

    ssl_certificate /etc/letsencrypt/live/aigenis-api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aigenis-api.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
```

## Приложение C: Kubernetes deployment (minimal)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aigenis-parser
spec:
  replicas: 1
  selector:
    matchLabels:
      app: aigenis-parser
  template:
    metadata:
      labels:
        app: aigenis-parser
    spec:
      containers:
      - name: parser
        image: aigenis-parser:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: aigenis-secret
              key: database-url
        - name: TELEGRAM_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: aigenis-secret
              key: telegram-bot-token
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2"
        livenessProbe:
          exec:
            command: ["python", "-m", "scraper", "health"]
          initialDelaySeconds: 30
          periodSeconds: 60
```
