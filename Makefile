# =============================================================================
# Aigenis Parser v3 SAAS — Makefile
# =============================================================================
# Использование:
#   make build          — сборка Docker-образа
#   make up             — запуск всех сервисов (parser + БД + Redis)
#   make up-bot         — + Telegram-бот
#   make up-api         — + REST API
#   make up-frontend    — + Frontend (nginx)
#   make up-saas        — полный SAAS стек (all + frontend)
#   make down           — остановка всех сервисов
#   make logs           — логи парсера
#   make once           — однократный сбор данных
#   make seo-sitemap    — сгенерировать sitemap.xml (нужен SEO_PUBLIC_BASE_URL)
#   make health         — health-check
#   make shell          — bash в контейнере парсера
#   make psql           — psql в контейнере PostgreSQL
#   make migrate        — выполнить миграции Alembic
#   make clean          — очистка томов (ВНИМАНИЕ: удалит все данные)
# =============================================================================

.PHONY: build up up-bot up-api up-frontend up-saas down logs once health migrate shell psql clean

# ---- Сборка ----

build:
	docker compose build --pull

build-frontend:
	docker compose build frontend

build-all:
	docker compose build --pull

build-nocache:
	docker compose build --no-cache --pull

# ---- Запуск ----

up:
	docker compose up -d

up-all:
	docker compose up -d frontend

up-api:
	docker compose up -d api

up-frontend:
	docker compose up -d frontend

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

logs-frontend:
	docker compose logs -f frontend

logs-all:
	docker compose logs -f

# ---- Команды парсера ----

once:
	docker compose run --rm parser once

once-usd:
	docker compose run --rm parser once --currency USD

history:
	docker compose run --rm parser backfill

seo-sitemap:
	docker compose run --rm parser seo-sitemap

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

# ---- SAAS утилиты ----

create-admin:
	docker compose run --rm parser python3 -c "
import asyncio
import os
import sys
sys.path.insert(0, '/app')
from scraper.db import session_scope
from scraper.orm import UserORM
from passlib.context import CryptContext

async def create_admin():
    async with session_scope() as session:
        from sqlalchemy import select
        result = await session.execute(select(UserORM).where(UserORM.email == os.getenv('ADMIN_EMAIL')))
        existing = result.scalar_one_or_none()
        if existing:
            print('Admin user already exists:', existing.email)
            return
        pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
        admin = UserORM(
            email=os.getenv('ADMIN_EMAIL'),
            name='System Administrator',
            password_hash=CryptContext(schemes=['bcrypt'], deprecated='auto').hash(os.getenv('ADMIN_PASSWORD')),
            role='admin',
            subscription_tier='enterprise',
            is_active=True,
            is_verified=True
        )
        session.add(admin)
        await session.commit()
        print('Admin user created:', admin.email)
asyncio.run(create_admin())
"

check-subscriptions:
	docker compose run --rm parser python3 -c "
import asyncio
import os
import sys
sys.path.insert(0, '/app')
from scraper.db import session_scope
from scraper.orm import SubscriptionORM, UserORM

async def check_subs():
    async with session_scope() as session:
        from sqlalchemy import select
        subs = await session.execute(select(SubscriptionORM, UserORM.email).join(UserORM, SubscriptionORM.user_id == UserORM.id))
        for sub, email in subs:
            print(f'User: {email} | Plan: {sub.plan} | Status: {sub.status} | Period: {sub.current_period_end}')
asyncio.run(check_subs())
"

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
	docker images aigenis-parser aigenis-frontend
