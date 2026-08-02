# Development Guide — Bonds Engine v4

## Prerequisites

- Python 3.13+
- PostgreSQL 16
- Redis 7
- Node.js 22 (for frontend)
- Docker (for containerized dev)

## Local Setup (without Docker)

```bash
# 1. Clone the repo
git clone <repo-url>
cd bonds-engine

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -e ".[dev,prod]"

# 4. Set up the database
createdb aigenis
# Or use Docker: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass -e POSTGRES_DB=aigenis postgres:16

# 5. Run migrations
alembic upgrade head

# 6. Set environment variables
cp .env.example .env
# Edit .env with your local values

# 7. Run the API
python -m uvicorn api.main:app --reload --port 8000

# 8. Run the bot (separate terminal)
python -m telegram_bot.bot

# 9. Run the scraper
python -m scraper run
```

## Running Tests

```bash
# Run all tests
pytest tests -v

# Run with coverage
pytest tests --cov=. --cov-report=html

# Run specific test file
pytest tests/test_api_endpoints.py -v

# Run tests matching a pattern
pytest tests -k "test_ml" -v
```

## Linting and Formatting

```bash
# Ruff (linting + auto-fix)
ruff check .
ruff check . --fix

# Ruff (formatting)
ruff format .

# MyPy (type checking — non-blocking in CI)
mypy .
```

## Code Conventions

- **No comments** unless explicitly asked (per project config)
- **Type hints** on all function signatures
- **Async/await** for all I/O operations
- **Literal types** for enums (e.g., `ModelKind`, `StrategyName`)
- **Pydantic models** for all request/response schemas
- **SQLAlchemy 2.0** patterns (select(), session.execute())
- **Russian variable names** for domain concepts (облигация, эмитент, купон)

## Project Structure for Development

```
bonds-engine/
├── api/                    # FastAPI app
│   ├── main.py            # Application entry point
│   ├── deps.py            # Dependencies (auth, DB session)
│   ├── routers/           # Route definitions
│   ├── schemas/           # Pydantic models
│   └── services/          # Business logic
├── scraper/               # Data collection
│   ├── pipeline.py        # Main scraper pipeline
│   ├── parsers/           # Bond-specific parsers
│   ├── db.py              # Database session management
│   └── sources/           # Data source adapters
├── ml/                    # Machine learning
│   ├── engine.py          # Training + prediction
│   ├── features.py        # Feature engineering
│   ├── models.py          # Pydantic/ML model types
│   └── repository.py      # Prediction storage
├── portfolio/             # Portfolio analytics
│   ├── pnl.py             # P&L calculation
│   ├── rebalance.py       # Auto-rebalancing
│   └── optimizer.py       # Capital allocation
├── forecast/              # Monte Carlo forecasting
│   └── engine.py
├── desk/                  # Fixed income analytics
│   ├── duration.py
│   ├── yield_curve.py
│   ├── relative_value.py
│   ├── carry.py
│   ├── repo.py
│   └── stress.py
├── telegram_bot/          # Telegram bot
│   ├── bot.py             # Bot entry point
│   ├── handlers/          # Command handlers
│   └── middleware/        # Telegram middleware
├── scoring/               # Reward/Risk scoring
├── recommendations/       # Bond recommendations
├── monitoring/            # Prometheus metrics
├── visualization/         # matplotlib charts
├── notifications/         # Email/SMS alerts
├── alembic/               # DB migrations
├── frontend/              # React SPA
│   ├── src/               # React components
│   ├── Dockerfile         # Frontend Docker build
│   └── nginx.conf         # nginx config
├── tests/                 # pytest tests
├── docker-compose.yml     # Full stack orchestration
├── Dockerfile             # Backend Docker image
└── pyproject.toml         # Project config, dependencies
```

## Adding a New Endpoint

1. Create a router in `api/routers/` or add to an existing one
2. Define Pydantic schemas for request/response in `api/schemas/`
3. Register the router in `api/main.py`
4. Add tests in `tests/`
5. Run `ruff check . --fix` and `ruff format .`

## Adding a New Migration

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## CI/CD

The CI pipeline runs:
1. `ruff check .` — blocking
2. `pytest tests -q --tb=no` — blocking
3. `mypy .` — non-blocking (pre-existing debt)
4. `alembic upgrade head` — blocking (migration check)

## Debugging

```bash
# View logs for a specific service
docker compose logs -f api

# Run a one-off command in a container
docker compose exec api python -c "from api.main import app; print(app.version)"

# Connect to the database
docker compose exec postgres psql -U aigenis -d aigenis

# Inspect Redis
docker compose exec redis redis-cli ping
```