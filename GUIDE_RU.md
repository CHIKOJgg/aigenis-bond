# Гайд по запуску Aigenis Parser — Bond Fixed Income Assistant

## Быстрый старт

### 1. Установка

```bash
# Клонировать репозиторий
git clone <repo> aigenis-parser
cd aigenis-parser

# Создать .env из примера
copy .env.example .env

# Установить зависимости
pip install -e .
pip install -e ".[dev]"

# Установить Chromium для Playwright
playwright install chromium
```

### 2. Запуск парсинга

```bash
# Однократный сбор данных по всем валютам
python -m scraper once

# По конкретной валюте
python -m scraper once --currency USD,BYN

# Догрузка истории за N дней
python -m scraper backfill --days 365

# Health-check
python -m scraper health
```

### 3. Запуск планировщика (cron)

```bash
python -m scraper run
```
Автоматически запускает:
- Каждые 6ч: парсинг + Score
- Ежедневно в 3:00: история
- Еженедельно: ML-train, Stress
- Ежедневно: Curve, RV

### 4. V4 Mini Fixed Income Desk

```bash
python -m scraper desk-curve        # Кривая доходности (Nelson-Siegel)
python -m scraper desk-rv           # Relative Value (rich/cheap)
python -m scraper desk-duration     # Duration портфеля
python -m scraper desk-duration --bond OP-51  # Duration облигации
python -m scraper desk-carry --funding 5.0    # Carry
python -m scraper desk-repo --bond OP-51 --notional 1000 --tenor 30  # РЕПО
python -m scraper desk-stress       # Стресс-тесты
python -m scraper desk-status       # Сводка
```

### 5. Telegram Bot

```bash
# Установить TELEGRAM_BOT_TOKEN в .env
python -m telegram_bot.bot
```

### 6. Docker

```bash
docker compose up -d                    # Parser + Postgres + Redis
docker compose --profile bot up -d      # + Telegram Bot
docker compose --profile init run alembic  # Миграции БД
```

### 7. Тесты

```bash
pytest                    # Все 98 тестов
pytest tests/test_desk.py # V4 Desk тесты (17 шт)
python verify_aigenis.py mock   # Проверка парсинга на фикстурах
python verify_aigenis.py sqlite # End-to-end на SQLite
```

---

## Проверка полноты парсинга

### Какие данные парсятся по каждой облигации

| Поле | Тип | Пример | Откуда берётся |
|------|-----|--------|----------------|
| **internal_id** | str | OP-51 | ID в системе Aigenis |
| **name** | str | ОП-51 | Название облигации |
| **issuer** | str | Министерство финансов | Эмитент |
| **currency** | str | USD | Валюта (USD/BYN/EUR/XAU/XAG/XPT) |
| **nominal** | Decimal | 1000 | Номинал |
| **coupon_rate** | Decimal | 5.25 | **Ставка купона (%)** |
| **coupon_frequency** | int | 2 | **Периодичность выплат (раз/год)** |
| **maturity_date** | date | 2030-06-15 | Дата погашения |
| **price** | Decimal | 98.5 | Текущая цена |
| **yield_to_maturity** | Decimal | 5.47 | **Доходность к погашению (%)** |
| **amortization** | str | none | Тип амортизации |
| **offer_date** | date | — | Дата оферты |
| **start_date** | date | 2024-06-15 | Дата размещения |
| **end_date** | date | 2030-06-15 | Дата окончания |
| **isin** | str | US0001OP51 | ISIN-код |
| **status** | str | active | Статус |
| **fetched_at** | datetime | 2026-06-18T10:00:00 | Время сбора |
| **raw** | dict | — | Полный сырой JSON |

### История (`BondHistory`)

| Поле | Описание |
|------|----------|
| **date** | Дата снимка |
| **price** | Цена на дату |
| **yield_** | Доходность на дату |
| **coupon** | Купон на дату |
| **status** | Статус на дату |

### Новые поля (V5 — расширенный парсинг)

Добавлены в модель и БД для максимально полного сбора данных:

| Поле | Тип | Описание |
|------|-----|----------|
| **registration_number** | str | Номер государственной регистрации (data-reg) |
| **issue_volume** | Decimal | Объём эмиссии |
| **issue_number** | int | Номер выпуска |
| **income_method** | enum | Способ выплаты дохода (coupon/discount/indexed/mixed) |
| **in_stock** | bool | В наличии (data-stock) |
| **guarantor** | str | Организация-гарант |
| **maturity_term_text** | str | Срок погашения текстом (data-vterm) |
| **coupon_description** | str | Полное описание купона (ставка + периодичность) |
| **coupon_schedule** | dict | График купонных выплат по годам |

### Производные метрики (Desk V4)

| Метрика | Описание |
|---------|----------|
| **Modified Duration** | Чувствительность цены к изменению доходности |
| **Macaulay Duration** | Средневзвешенный срок денежных потоков |
| **Convexity** | Выпуклость (вторая производная цены) |
| **DV01** | Изменение цены при сдвиге YTM на 1bp |
| **Key Rate Durations** | Чувствительность к сдвигам на отдельных сроках |
| **Nelson-Siegel Curve** | Параметры кривой доходности (β₀, β₁, β₂, τ) |
| **Z-score (RV)** | Relative Value сигнал относительно группы |
| **Carry P&L** | Ожидаемая доходность от купона + rolldown |
| **Haircut (РЕПО)** | Дисконт по типу эмитента |
| **Stress P&L** | Результаты 7 стресс-сценариев |

### Вывод

**Парсинг собирает максимально подробную информацию по каждой облигации:**
- ✅ Ставка купона и периодичность
- ✅ Доходность к погашению (YTM)
- ✅ Цена, номинал, валюта
- ✅ Даты: погашения, размещения, оферты, начала/окончания
- ✅ ISIN, статус, эмитент
- ✅ Амортизация
- ✅ История цен и доходности
- ✅ Сырой JSON для отладки
- ✅ Дополнительные поля из DOM (объём эмиссии, способ выплаты дохода)

**Все тесты парсинга проходят — 29 проверок mock (включая 9 новых полей) + 10 unit-тестов парсеров.**
**98 тестов проекта проходят полностью.**
