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

.PHONY: build up up-bot up-api up-frontend up-saas down logs once health migrate shell psql clean verify verify-e2e

# ---- Проверка качества (clean bill of health) ----
verify:
	@echo "=== Ruff check ==="
	python -m ruff check .
	@echo "=== Ruff format check ==="
	python -m ruff format --check .
	@echo "=== Size budget check ==="
	python scripts/check_size_budget.py
	@echo "=== Mypy (informational; type-debt baseline) ==="
	-python -m mypy api/aigenis scraper/providers scoring portfolio
	@echo "=== Pytest ==="
	python -m pytest
	@echo "=== Frontend lint ==="
	cd frontend && npm run lint
	@echo "=== Frontend tests ==="
	cd frontend && npm run test
	@echo "=== Frontend build ==="
	cd frontend && npm run build
	@echo "=== All checks passed ==="

# ---- E2E smoke + visual regression + perf (требует установленных браузеров Playwright) ----
verify-e2e:
	cd frontend && npm run test:e2e
	cd frontend && npm run test:e2e:visual
	cd frontend && npm run test:e2e:perf

# ---- Reproducible pre-demo audit chain (Windows: pwsh -File scripts/demo-audit.ps1) ----
.PHONY: demo-audit
demo-audit:
	@echo "=== 1/8 Fixture consistency (audit_demo: regenerate + two-copy sync) ==="
	.venv/bin/python audit_demo.py
	@echo "=== 2/8 Optimizer monotonicity (verify_demo_frontend) ==="
	.venv/bin/python verify_demo_frontend.py
	@echo "=== 3/8 Backend demo tests ==="
	.venv/bin/python -m pytest tests/test_demo_endpoint.py tests/test_demo_components.py tests/test_analytics_http.py -q
	@echo "=== 4/8 Ruff (demo surface) ==="
	.venv/bin/python -m ruff check api/demo.py tests/test_demo_endpoint.py tests/test_demo_components.py tests/test_analytics_http.py audit_demo.py verify_demo_frontend.py
	@echo "=== 5/8 Frontend lint + typecheck ==="
	cd frontend && npm run lint && npx tsc -b
	@echo "=== 6/8 Frontend unit tests ==="
	cd frontend && npm run test
	@echo "=== 7/8 E2E smoke + visual regression + perf ==="
	cd frontend && npm run test:e2e && npm run test:e2e:visual && npm run test:e2e:perf
	@echo "=== 8/8 Security grep (hardcoded secrets in demo surface) ==="
	@! grep -rInE "(api[_-]?key|apikey|secret|passwd|password|bearer|auth[_-]?token|access[_-]?token)[[:space:]]*[:=][[:space:]]*[\"'][^\"']{8,}[\"']" frontend/src/demo api --include='*.ts' --include='*.tsx' --include='*.py' && { echo "Security grep clean."; true; }
	@echo "=== Demo audit chain passed ==="

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
	docker compose run --rm parser python3 -m scraper once

once-usd:
	docker compose run --rm parser python3 -m scraper once --currency USD

history:
	docker compose run --rm parser python3 -m scraper backfill

seo-sitemap:
	docker compose run --rm parser python3 -m scraper seo-sitemap

health:
	docker compose run --rm parser python3 -m scraper health

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
	docker compose run --rm parser python3 -m scraper desk-curve

desk-rv:
	docker compose run --rm parser python3 -m scraper desk-rv

desk-stress:
	docker compose run --rm parser python3 -m scraper desk-stress

desk-car:
	docker compose run --rm parser python3 -m scraper desk-carry --funding ${FUNDING:-5.0}

# ---- Утилиты ----

status:
	docker compose ps

images:
	docker images aigenis-parser aigenis-frontend
