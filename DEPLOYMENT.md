# Deployment Guide — Aigenis Parser

Полное руководство по развёртыванию Aigenis Parser в production. Стек собирается
через Docker Compose: PostgreSQL + Redis + Parser (scraper/scheduler) + REST API +
опционально Telegram-бот и фронтенд (nginx).

Язык конфигов — `.env`, секреты генерируются скриптом. Все сервисы используют один
образ `aigenis-parser:latest` (кроме фронтенда и БД).

---

## 1. Требования

- Linux-сервер (Ubuntu 22.04+ рекомендуется) с доступом по SSH.
- Установленные **Docker Engine** ≥ 24 и **Docker Compose** ≥ v2 (`docker compose version`).
- (Опционально) домен, если нужен публичный HTTPS через Certbot или Cloudflare Tunnel.
- Порты: `80`/`443` для фронтенда (или только `127.0.0.1` + туннель), `5432` (БД, на localhost).

> Память: минимум ~3 ГБ (parser до 2 ГБ + БД 512 МБ + остальные). Для продакшена —
> выделите 4 ГБ+.

---

## 2. Подготовка окружения

Клонируйте репозиторий и создайте `.env` из шаблона:

```bash
git clone https://github.com/CHIKOJgg/aigenis-bond.git
cd aigenis-bond
cp .env.example .env
```

Сгенерируйте криптографически стойкие секреты (записывает в `.env`, создаёт бэкап
`.env.bak`):

```bash
python scripts/generate_secrets.py --write-env
```

Это заполнит `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
и `ENCRYPTION_KEY` и пропишет пароли в `DATABASE_URL`/`REDIS_URL`.

Затем отредактируйте `.env` и задайте как минимум:

| Переменная | Назначение |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather (нужен для бота и оплаты Stars) |
| `TELEGRAM_BOT_USERNAME` | Имя бота без `@` — для deep-link «Подписаться» на сайте |
| `AIGENIS_WEB_URL` / `_USERNAME` / `_PASSWORD` | Учётные данные сайта-источника (если парсинг требует логина) |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Платежи картами/СБП (опц.) |
| `STARS_PRO` / `STARS_ENTERPRISE` | Цена подписок в Telegram Stars |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Админ-аккаунт (создаётся на старте) |
| `SMTP_*` | Email-уведомления (опц.) |
| `CORS_ORIGINS` | Разрешённые фронтенд-домены, через запятую |
| `SENTRY_DSN` | Трекинг ошибок (опц.) |
| `REFERRAL_BONUS_DAYS` | Бонус дней пробного к пригласившему (рефералка), деф. 3 |
| `REFERRAL_COMMISSION_PCT` | Комиссия партнёра с конверсии (affiliate), деф. 0 |
| `DEMO_MODE` | Публичный DEMO-режим (read-only, watermark), `1/true/yes` |
| `FALLBACK_SOURCE` | Альтернативный источник котировок при недоступности платного |
| `SEO_PUBLIC_BASE_URL` | Канонический публичный домен для `sitemap.xml` (напр. `https://bonds.aigenis.by`). Если задан — планировщик перегенерирует кэш-файл sitemap после каждого парсинга, иначе sitemap рендерится на лету. |
| `SEO_SITEMAP_PATH` | Путь к кэш-файлу sitemap (деф. temp-каталог). Задайте, если хотите отдавать `/sitemap.xml` как статику через nginx. |

> Никогда не коммитьте `.env` — он в `.gitignore`.

---

## 3. Сборка образов

```bash
docker compose build --pull
```

Собираются: `aigenis-parser:latest` (Python + Playwright + собранный фронтенд внутри)
и `aigenis-frontend:latest` (nginx). Первый билд занимает несколько минут (установка
Playwright Chromium и `npm ci`).

---

## 4. Запуск

### Минимальный стек (фоновый сбор + БД + Redis + API)

```bash
docker compose up -d
```

Запустятся: `postgres`, `redis`, `parser` (с планировщиком), `api`.
Миграции Alembic и админ-пользователь создаются автоматически в `docker-entrypoint.sh`.

### Профили

| Команда | Что поднимает |
|---|---|
| `docker compose up -d` | core: postgres, redis, parser, api |
| `docker compose --profile bot up -d bot` | Telegram-бот |
| `docker compose up -d frontend` | фронтенд (nginx, порты 80/443) |
| `docker compose --profile tunnel up -d cloudflared` | Cloudflare Tunnel (публичный HTTPS без портов) |
| `docker compose --profile certbot run --rm certbot ...` | выпуск/обновление Let's Encrypt сертификата |

Полный SAAS-стек:

```bash
docker compose up -d
docker compose --profile bot up -d bot
docker compose up -d frontend
```

Проверить статус: `docker compose ps` (или `make status`).

---

## 5. База данных и миграции

Миграции применяются автоматически при старте каждого сервиса (entrypoint). Вручную:

```bash
docker compose run --rm parser alembic upgrade head
```

Создать админа вручную (если не заданы `ADMIN_EMAIL`/`ADMIN_PASSWORD`):

```bash
make create-admin
```

Проверить подписки: `make check-subscriptions`.

---

## 6. HTTPS

Два варианта — выберите один.

### Вариант A — Cloudflare Tunnel (рекомендуется, без портов/SSL)

Работает за NAT/CGNAT, даёт валидный TLS бесплатно.

1. Создать туннель: <https://dash.cloudflare.com> → Access → Tunnels → Create.
2. Скопировать токен в `.env`: `CLOUDFLARED_TUNNEL_TOKEN=eyJ...`.
3. В настройках Public Hostname туннеля указать:
   `Type=HTTPS`, `URL=frontend:443`, включить **No TLS Verify**
   (nginx использует self-signed сертификат; TLS терминирует сам туннель).
4. Запустить:

```bash
docker compose --profile tunnel up -d cloudflared
```

### Публичный DEMO-режим (продажа компании / ознакомление)

Чтобы показать весь продукт потенциальному покупателю (Трек A) без выдачи
доступа к аккаунту, включите DEMO-режим. Анонимные посетители получают
read-only полный доступ (тир `demo`), фронтенд показывает водяной знак
«DEMO».

1. В `.env` установите:

   ```bash
   DEMO_MODE=1
   ```

2. Запустите публичный Cloudflare Tunnel (вариант A выше) на отдельный
   поддомен, например `demo.aigenis.by`.
3. Фронтенд показывает баннер DEMO при `?demo=1` или если хост начинается с
   `demo`. Готовые материалы для рассылки buyer/партнёрам — в `docs/sales/`
   (`one_pager.md`, `teaser.md`).

> DEMO-режим не требует платного логина на сайт-источник: если
> `AIGENIS_WEB_USERNAME/PASSWORD` не заданы, парсер переходит в stale-режим
> (отдаёт уже сохранённые данные) вместо падения. Для диверсификации источника
> настройте `FALLBACK_SOURCE` (адаптер в `scraper/fallback_source.py`).
>

### Источник данных: MOEX (публичный, без логина)

Продукт может собирать живые котировки с MOEX ISS без платной подписки:

- `DATA_SOURCE=moex` — только MOEX; `aigenis` — только платный источник;
  `both` — оба.
- `MOEX_BOARDS=TQCB,TQOB` — RUB корпоративы (TQCB) + USD/EUR евробонды (TQOB).
- Реализация: `scraper/moex.py` (`MoexClient`), нативный pipeline
  `scraper/pipeline.py:run_once_moex`, CLI: `python -m scraper moex`.
- Собирается: живые котировки (цена/YTM), история цен и YTM (`history` блок ISS),
  купонный календарь (bondization endpoint, поле `coupondate`).
- Охват: RUB корпоративные облигации + еврооблигации в USD/EUR. BYN по-прежнему
  через платный источник; расширение на другие рынки — подключением новых фидов.

> Готовый адаптер: `FALLBACK_SOURCE=moex` — публичный MOEX ISS API (без ключа,
> RUB-корпоративные облигации, board `TQCB`). При недоступности платного
> источника парсер сам подтянет котировки MOEX и сохранит их в БД. Требует
> сетевого доступа и соблюдения rate-limit MOEX. Тонкая настройка:
> `FALLBACK_MOEX_BOARD`, `FALLBACK_MOEX_TIMEOUT`.

### Быстрый запуск без вложений (MOEX + DEMO_MODE)

`docker-compose.yml` по умолчанию ставит `DATA_SOURCE=moex` и `DEMO_MODE=1`, поэтому
`docker compose up -d` поднимает рабочий продукт **без платных ключей и логинов**:

```bash
cp .env.example .env            # при необходимости задайте POSTGRES_PASSWORD
docker compose up -d postgres redis parser api frontend
# парсер сам соберёт RUB-корпоративы (TQCB) + USD/EUR евробонды (TQOB) с MOEX ISS
docker compose run --rm parser moex          # однократный сбор из MOEX
docker compose run --rm parser health         # проверка
```

Публичный доступ без белого IP и платного SSL — через Cloudflare Tunnel:
`CLOUDFLARED_TUNNEL_TOKEN=... docker compose --profile tunnel up -d cloudflared`
(или `docker compose --profile quick-tunnel up -d cloudflared-quick` для временного
`*.trycloudflare.com` URL). DEMO_MODE включает водяной знак и throttle на бэкенде.

> Платный источник aigenis.by подключается отдельно: `DATA_SOURCE=both` + логин в `.env`.
> Бот и платежи (YooKassa/Stars) опциональны и не нужны для демо.

---

Требует домен с A-записью на IP сервера и открытые порты 80/443.

```bash
# 1. Поднять фронтенд (nginx отдаёт ACME-challenge на 80)
docker compose up -d frontend

# 2. Выпустить сертификат
docker compose --profile certbot run --rm certbot certonly \
  --webroot-path /var/www/certbot \
  --email admin@example.com -d your-domain.com --agree-tos --no-eff-email

# 3. Перезапустить фронтенд, чтобы подхватить certs
docker compose restart frontend
```

Certbot автоматически обновляет сертификаты (cron внутри контейнера).
HSTS в `frontend/nginx.conf` выключен по умолчанию — раскомментируйте после проверки.

---

## 6.1 Публичные SEO-страницы и индексация

Продукт отдаёт бесплатные server-rendered страницы (`/bonds`, `/bonds/{id}`,
`/partners`, `/sitemap.xml`, `/robots.txt`) — органический канал без бюджета
(см. `docs/sales/cmo_audit.md`, §2/§6).

Чтобы поисковики их нашли:

1. **Отдайте `sitemap.xml` и `robots.txt` на каноническом домене.**
   `robots.txt` уже указывает `Sitemap: <domain>/sitemap.xml`. Если включили
   `SEO_PUBLIC_BASE_URL`, планировщик (`scraper.scheduler.scheduled_job`)
   перегенерирует кэш-файл `sitemap.xml` после каждого парсинга; при желании
   отдавайте его как статику через nginx (путь задаётся `SEO_SITEMAP_PATH`).
   Разовая генерация: `make seo-sitemap` (или `docker compose run --rm parser seo-sitemap`).
2. **Зарегистрируйте сайт в Google Search Console** и Яндекс.Вебмастер и
   отправьте `https://<ваш-домен>/sitemap.xml` на индексацию. Без этого шага
   органический трафик не пойдёт — страницы существуют, но краулеры о них не знают.
3. **Канонический домен.** Задайте `SEO_PUBLIC_BASE_URL=https://<домен>` (без
   слэша), чтобы абсолютные URL в sitemap и JSON-LD были корректны. Без него
   sitemap рендерится на лету по домену входящего запроса (тоже работает, но
   менее предсказуемо для повторной индексации).
4. **Внутренние ссылки.** Лендинг веб-приложения и виджет содержат ссылку
   «Для бизнеса» → `/partners`; страницы `/bonds` и `/partners` перекрёстно
   ссылаются друг на друга — это ускоряет обход и передачу веса.

---

## 7. Telegram-бот

Бот запускается профилем `bot`. Для webhook-режима задайте в `.env`:

```
WEBHOOK_URL=https://your-domain.com
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8080
```

и пробросьте `/webhook/` через nginx (уже настроено в `frontend/nginx.conf`).
При long-polling (по умолчанию) `WEBHOOK_URL` оставьте пустым.

Запуск: `docker compose --profile bot up -d bot`. Логи: `docker compose logs -f bot`.

---

## 8. Проверка здоровья

Каждый сервис имеет Docker healthcheck:

- `api` → `GET /health` (внутри контейнера `curl -f http://localhost:8000/health`).
- `parser` → `python -m scraper health`.
- `bot` → процесс `telegram_bot.bot` запущен.
- `postgres` / `redis` → нативные ping/ready.

Снаружи:

```bash
curl -f http://localhost/health      # фронтенд проксирует на API
docker compose ps                    # колонка STATUS = healthy
```

Фоновые однократные команды:

```bash
make once          # однократный сбор данных
make health        # health-check парсера
make desk-curve    # пересчёт кривой доходности
make logs          # логи парсера (follow)
```

---

## 9. Обновление (deploy новой версии)

```bash
git pull
docker compose build --pull
docker compose up -d
docker compose --profile bot up -d bot
```

Entrypoint сам накатит новые миграции Alembic при старте. Для минимизации простоя
можно обновлять сервисы по очереди (`docker compose up -d api`, затем `parser` и т.д.).

Очистка неиспользуемых образов: `docker image prune -f`.

---

## 10. Мониторинг

Prometheus (`:9090`) и Grafana (`:3001`) привязаны к `127.0.0.1` — **не экспонируйте
наружу**. Смотреть локально на сервере или через SSH-туннель:

```bash
ssh -L 9090:127.0.0.1:9090 -L 3001:127.0.0.1:3001 user@server
```

- Prometheus: <http://localhost:9090> (scrape-конфиг: `docker/prometheus/prometheus.yml`).
- Grafana: <http://localhost:3001> (логин/пароль — `GF_SECURITY_ADMIN_USER`/`_PASSWORD`,
  по умолчанию пароль пустой — задайте `GRAFANA_ADMIN_PASSWORD`).

Метрики бота (`bot_commands_total`, `bot_errors_total`) и `/metrics` API поднимаются
на `BOT_METRICS_PORT` (0 = выключить).

---

## 11. Бэкапы

PostgreSQL-данные в томе `aigenis-pgdata`. Бэкап:

```bash
docker compose exec -T postgres pg_dump -U aigenis aigenis > backup_$(date +%F).sql
```

Восстановление:

```bash
docker compose exec -T postgres psql -U aigenis aigenis < backup_YYYY-MM-DD.sql
```

Логи приложения — в томе `aigenis-logs` (`/app/logs`).

---

## 12. Troubleshooting

| Симптом | Причина / решение |
|---|---|
| Сервис не стартует, лог: `JWT_SECRET_KEY is not set` | В `production` окружении (`AIGENIS_ENVIRONMENT=production`) обязателен `JWT_SECRET_KEY`. Запустите `scripts/generate_secrets.py --write-env`. |
| `POSTGRES_PASSWORD is required` | Задайте `POSTGRES_PASSWORD` в `.env` (генерируется скриптом). |
| Parser падает с `pg_isready` / timeout к БД | БД ещё не healthy — подождите, `docker compose ps`. Entrypoint ждёт до 30 попыток. |
| Бот не отвечает | Проверьте `TELEGRAM_BOT_TOKEN`; `docker compose logs -f bot`. При webhook — доступность `WEBHOOK_URL`. |
| Фронтенд показывает paywall вместо данных | Пользователь free-тира; Pro/Enterprise эндпоинты отдают `402`. Проверьте подписку: `make check-subscriptions`. |
| Certbot: `Timeout` при выпуске | Домен не резолвится на IP или порт 80 закрыт фаерволом. |
| `502` на `/api/*` | API не healthy или упал. `docker compose logs -f api`. |

Для полной отладки: `docker compose logs -f` (все сервисы) или `make logs-all`.

---

## 13. Переменные ресурсов (опц.)

Лимиты памяти задаются в `.env` (см. `.env.example`, секция «Docker-only: Resource
Limits»): `POSTGRES_MEM_LIMIT`, `PARSER_MEM_LIMIT`, `API_MEM_LIMIT`, `BOT_MEM_LIMIT`,
`FRONTEND_MEM_LIMIT`, `REDIS_MAX_MEMORY`. Подстройте под размер сервера.
