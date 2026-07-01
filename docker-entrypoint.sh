#!/bin/bash
set -e

# =============================================================================
# Aigenis Parser — Docker entrypoint
# =============================================================================
# Выполняет миграции БД при старте, затем запускает указанную команду.

echo "[entrypoint] Aigenis Parser v2 starting..."

# 1. Проверка обязательных переменных
if [ -z "$DATABASE_URL" ]; then
    echo "[entrypoint] FATAL: DATABASE_URL is not set"
    exit 1
fi

# 2. Ожидание PostgreSQL
if echo "$DATABASE_URL" | grep -q "postgresql"; then
    echo "[entrypoint] Waiting for PostgreSQL..."
    # Извлекаем хост и порт из DSN
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

# 3. Выполнение миграций Alembic
echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete"

# 4. Запуск указанной команды
echo "[entrypoint] Executing: $@"
exec "$@"
