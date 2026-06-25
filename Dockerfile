FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# --- Build stage ---
FROM base AS builder

COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install --no-warn-script-location build wheel \
    && python -m build --wheel --no-isolation 2>/dev/null || true

# --- Runtime stage ---
FROM base AS runtime

COPY --from=builder /app/dist /tmp/dist

# Install from wheel if available, otherwise via pip install .
RUN pip install --upgrade pip \
    && if ls /tmp/dist/*.whl 2>/dev/null; then \
         pip install /tmp/dist/*.whl; \
       else \
         pip install .; \
       fi \
    && pip install ".[dev]" \
    && playwright install chromium

# Application code (overrides installed package for development)
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

RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

ENV AIGENIS_LOG_FILE=/app/logs/scraper.log

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -m scraper health || exit 1

ENTRYPOINT ["python", "-m", "scraper"]
CMD ["run"]
