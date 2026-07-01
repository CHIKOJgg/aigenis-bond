# =============================================================================
# Aigenis Parser v2 — Production-grade Docker image
# =============================================================================
# База: официальный образ Playwright с Chromium
# Внимание: образ использует Ubuntu Jammy (Python 3.10).
# Ниже устанавливается Python 3.13 через deadsnakes PPA.
# =============================================================================
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Minsk

WORKDIR /app

# ---------------------------------------------------------------------------
# 1. Системные зависимости + Python 3.13 через deadsnakes PPA
# ---------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        software-properties-common \
        gpg-agent \
        curl \
        ca-certificates \
        netcat-openbsd \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        python3.13 \
        python3.13-dev \
        python3.13-venv \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем python3.13 как системный python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
    && update-alternatives --set python3 /usr/bin/python3.13

# Устанавливаем pip для Python 3.13
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.13 \
    && rm -rf /root/.cache/pip

# ---------------------------------------------------------------------------
# 2. Установка зависимостей Python (кэшируется, пока не изменён pyproject.toml)
# ---------------------------------------------------------------------------
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install . \
    && pip install ".[dev]" \
    && playwright install chromium \
    && rm -rf /root/.cache/pip

# ---------------------------------------------------------------------------
# 3. Код приложения
# ---------------------------------------------------------------------------
COPY scraper ./scraper
COPY desk ./desk
COPY forecast ./forecast
COPY ml ./ml
COPY monitoring ./monitoring
COPY notifications ./notifications
COPY portfolio ./portfolio
COPY recommendations ./recommendations
COPY scoring ./scoring
COPY telegram_bot ./telegram_bot
COPY visualization ./visualization
COPY api ./api
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/

# ---------------------------------------------------------------------------
# 4. Финальная настройка
# ---------------------------------------------------------------------------
RUN mkdir -p /app/logs \
    && groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser

ENV AIGENIS_LOG_FILE=/app/logs/scraper.log \
    AIGENIS_ENVIRONMENT=production

# ---------------------------------------------------------------------------
# 5. Healthcheck
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -m scraper health || exit 1

# ---------------------------------------------------------------------------
# 6. Точка входа
# ---------------------------------------------------------------------------
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "-m", "scraper", "run"]
