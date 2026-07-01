# =============================================================================
# Aigenis Parser v2 — Makefile
# =============================================================================
# Использование:
#   make build          — сборка Docker-образа
#   make up             — запуск всех сервисов (парсер + БД + Redis)
#   make up-bot         — + Telegram-бот
#   make up-api         — + REST API
#   make up-all         — все сервисы
#   make down           — остановка всех сервисов
#   make logs           — логи парсера
#   make once           — однократный сбор данных
#   make health         — health-check
#   make shell          — bash в контейнере парсера
#   make psql           — psql в контейнере PostgreSQL
#   make migrate        — выполнить миграции Alembic
#   make clean          — очистка томов (ВНИМАНИЕ: удалит все данные)
# =============================================================================

.PHONY: build up up-bot up-api up-all down logs once health migrate shell psql clean

# ---- Сборка ----

build:
	docker compose build --pull parser

build-nocache:
	docker compose build --no-cache --pull parser

# ---- Запуск ----

up:
	docker compose up -d

up-bot:
	docker compose --profile bot up -d

up-api:
	docker compose --profile api up -d

up-all:
	docker compose --profile all up -d

# ---- Остановка ----

down:
	docker compose down

down-volumes:
	docker compose down -v

# ---- Логи ----

logs:
	docker compose logs -f parser

logs-bot:
	docker compose logs -f bot

logs-api:
	docker compose logs -f api

# ---- Команды парсера ----

once:
	docker compose run --rm parser once

once-usd:
	docker compose run --rm parser once --currency USD

history:
	docker compose run --rm parser backfill

health:
	docker compose run --rm parser health

shell:
	docker compose run --rm parser /bin/bash

# ---- База данных ----

psql:
	docker compose exec postgres psql -U ${POSTGRES_USER:-aigenis} -d ${POSTGRES_DB:-aigenis}

migrate:
	docker compose run --rm parser alembic upgrade head

migrate-downgrade:
	docker compose run --rm parser alembic downgrade -1

migrate-history:
	docker compose run --rm parser alembic history

# ---- Очистка ----

clean:
	docker compose down -v
	docker system prune -f

# ---- Desk-команды ----

desk-curve:
	docker compose run --rm parser desk-curve

desk-rv:
	docker compose run --rm parser desk-rv

desk-stress:
	docker compose run --rm parser desk-stress

desk-car:
	docker compose run --rm parser desk-carry --funding ${FUNDING:-5.0}

# ---- Утилиты ----

status:
	docker compose ps

images:
	docker images aigenis-parser
