FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY pyproject.toml ./
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
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --upgrade pip \
    && pip install . \
    && playwright install chromium

RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

ENV AIGENIS_LOG_FILE=/app/logs/scraper.log

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -m scraper health || exit 1

CMD ["python", "-m", "scraper", "run"]
