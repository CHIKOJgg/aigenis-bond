#!/bin/bash
set -e

# =============================================================================
# Aigenis Parser v3 — Docker entrypoint
# =============================================================================
# Performs DB migrations at startup, creates admin user if needed, then runs command.

echo "[entrypoint] Aigenis Parser v3 starting..."

# 1. Check required variables
if [ -z "$DATABASE_URL" ]; then
    echo "[entrypoint] FATAL: DATABASE_URL is not set"
    exit 1
fi

# 2. Wait for PostgreSQL
if echo "$DATABASE_URL" | grep -q "postgresql"; then
    echo "[entrypoint] Waiting for PostgreSQL..."
    DB_HOST=$(echo "$DATABASE_URL" | sed -n 's/.*@\([^:]*\).*/\1/p')
    DB_PORT=$(echo "$DATABASE_URL" | sed -n 's/.*:\([0-9]*\)\/.*/\1/p')
    DB_PORT=${DB_PORT:-5432}

    if [ -n "$DB_HOST" ]; then
        for i in $(seq 1 30); do
            if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
                echo "[entrypoint] PostgreSQL is ready (attempt $i)"
                break
            fi
            echo "[entrypoint] Waiting for PostgreSQL... ($i/30)"
            sleep 2
        done
    fi
fi

# 3. Run Alembic migrations
echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete"

# 4. Create initial admin user if configured
if [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PASSWORD" ]; then
    echo "[entrypoint] Checking/creating admin user..."
    python3 -c "
import asyncio
import os
import sys
sys.path.insert(0, '/app')
from scraper.db import session_scope
from scraper.orm import UserORM
from passlib.context import CryptContext

async def create_admin():
    async with session_scope() as session:
        # Check if admin exists
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
            password_hash=pwd_context.hash(os.getenv('ADMIN_PASSWORD')),
            role='admin',
            subscription_tier='enterprise',
            is_active=True,
            is_verified=True
        )
        session.add(admin)
        await session.commit()
        print('Admin user created:', admin.email)

asyncio.run(create_admin())
" || echo "[entrypoint] WARNING: Admin user creation failed (may already exist)"
fi

# 4. Execute specified command
echo "[entrypoint] Executing: \$@"
exec "\$@"
