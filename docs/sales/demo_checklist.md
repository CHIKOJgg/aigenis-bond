# Demo Checklist — Bonds Engine для Aigenis

## Цель

Поднять публичный demo-инстанс Bonds Engine, чтобы Олег Сафроненко
(и другие ЛПР) могли «пощупать» продукт до созвона.

## Требования

- Linux-сервер (минимум 2 CPU, 4 GB RAM, 20 GB SSD)
- Docker Engine ≥ 24 + Docker Compose v2
- Доступ в интернет (для MOEX ISS + Cloudflare Tunnel)

## Шаг 1: Подготовка сервера

```bash
# Установка Docker (если нет)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Выйти и зайти заново (или newgrp docker)
```

## Шаг 2: Клонирование и настройка

```bash
git clone https://github.com/CHIKOJgg/bonds-engine.git
cd aigenis-bond
cp .env.example .env
```

## Шаг 3: Конфигурация .env (демо-режим)

Убедись, что в `.env` стоят эти значения:

```ini
# --- Источник данных (MOEX — бесплатно, без логина) ---
DATA_SOURCE=moex
MOEX_BOARDS=TQCB,TQOB
MOEX_CAP=1000

# --- Демо-режим (read-only, watermark) ---
DEMO_MODE=1
# ОБЯЗАТЕЛЬНО: при AIGENIS_ENVIRONMENT=production + DEMO_MODE=1 API
# откажется стартовать (fail-closed защита paywall). Для демо — demo.
AIGENIS_ENVIRONMENT=demo

# --- SEO (для sitemap и индексации) ---
SEO_PUBLIC_BASE_URL=https://demo.твой-домен.com

# --- PostgreSQL (сгенерировать пароль) ---
# python scripts/generate_secrets.py --write-env
POSTGRES_PASSWORD=<сгенерировать>

# --- Остальное можно оставить пустым ---
# TELEGRAM_BOT_TOKEN, YOOKASSA_* не обязательны для демо
```

Сгенерировать секреты:
```bash
python scripts/generate_secrets.py --write-env
```

## Шаг 4: Запуск

```bash
# Поднять стек
docker compose up -d postgres redis parser api frontend

# Первичный сбор данных с MOEX
docker compose run --rm parser moex --currency RUB,USD,EUR

# Проверка здоровья
curl -f http://localhost/health
docker compose ps
```

## Шаг 5: Публичный доступ (Cloudflare Tunnel)

### Вариант A: Quick Tunnel (0 конфигурации, временный URL)

```bash
docker compose --profile quick-tunnel up -d cloudflared-quick
docker compose logs -f cloudflared-quick
# Ищи строку:  https://<рандом>.trycloudflare.com
```

Этот URL можно сразу отправить Олегу.

### Вариант B: Production Tunnel (постоянный домен)

1. Зайти в `dash.cloudflare.com` → Access → Tunnels → Create a tunnel
2. Выбрать `cloudflared`, дать имя `bonds-engine-demo`
3. Скопировать токен
4. В `Public Hostname`: `Type=HTTPS, URL=frontend:443`, включить `No TLS Verify`
5. В `.env` добавить: `CLOUDFLARED_TUNNEL_TOKEN=eyJ...`
6. Запустить:
```bash
docker compose --profile tunnel up -d cloudflared
```

## Шаг 6: Проверка демо

Открыть публичный URL в браузере, проверить:

- [ ] Главная — `/` — дашборд загружается
- [ ] Облигации — `/bonds` — список 1500+ облигаций
- [ ] Карточка облигации — кликнуть любую — score, YTM, купон, погашение
- [ ] Fixed Income Desk — `/desk` — кривая, duration, RV, carry
- [ ] Водяной знак — `DEMO` отображается на страницах
- [ ] SEO-страницы — `/bonds/{id}` открывается без JS (серверный рендеринг)
- [ ] Paywall — попробовать Pro-эндпоинт → `402` + предложение подписки
- [ ] AI-чат — открыть, спросить «что купить?» и «расскажи про BCSE-00427» — отвечает
- [ ] Новости — открыть карточку MOEX-облигации → вкладка «Новости» с реальными записями
- [ ] Язык — переключить RU → EN → BY — интерфейс переводится полностью
- [ ] Цены — лендинг: Free «0 BYN», Pro «BYN/мес или N Stars» — без мешанины валют
- [ ] Обновление — F5 на дашборде: не должно «мигать» старая версия (SW удалён)

## Шаг 7: Отправка ссылки Олегу

Шаблон сообщения (telegram/linkedin/email):

```
Олег, демо-версия Bonds Engine доступна по ссылке:
{URL}

Это живой продукт с реальными данными MOEX. Всё работает без
регистрации — можно сразу посмотреть.

Особого внимания заслуживает Fixed Income Desk (кривая доходности,
RV, стресс-тесты) — такого у Aigenis сейчас нет.
```

## Готовность к продаже

Перед звонком с Олегом убедись:

- [ ] Демо работает, данные свежие (не старше 6 часов)
- [ ] One-pager (`docs/sales/one_pager_v2.md`) под рукой
- [ ] Цены определены ($25k / $45k / $65k)
- [ ] Готовность к возражениям (см. `outreach_template_v2.md`)
- [ ] Позиция по источникам данных продумана (см. `data_licensing_position.md`)
- [ ] NDA-шаблон (если потребуется перед раскрытием кода)
