# =============================================================================
# Aigenis Parser v2 — Production-grade Docker image
# =============================================================================
# Multi-stage build:
#   1. frontend — builds Vite/React frontend
#   2. base — installs Python dependencies
#   3. final — minimal production image
# =============================================================================

# ---- Stage 1: Frontend build ----
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# ---- Stage 2: Python base ----
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Minsk

WORKDIR /app

# System dependencies + Python 3.13
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
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
    && update-alternatives --set python3 /usr/bin/python3.13 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.13 \
    && rm -rf /root/.cache/pip

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --upgrade pip \
    && pip install . \
    && pip install ".[prod]" \
    && playwright install chromium \
    && rm -rf /root/.cache/pip

# Application code
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

# ---- Stage 3: Final image ----
FROM base AS final

RUN mkdir -p /app/logs \
    && groupadd -r appuser \
    && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy frontend build from stage 1
COPY --from=frontend /build/dist /app/frontend/dist

USER appuser

ENV AIGENIS_LOG_FILE=/app/logs/scraper.log \
    AIGENIS_ENVIRONMENT=production \
    FRONTEND_DIR=/app/frontend/dist

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -m scraper health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "-m", "scraper", "run"]
