# Deployment Guide - Aigenis Parser v3.0 SAAS

## Overview

This guide provides step-by-step instructions for deploying Aigenis Parser v3.0 as a Production Ready SAAS with authentication, Stripe payments, admin panel, and subscription management.

**GitHub Repository:** https://github.com/CHIKOJgg/aigenis-bond

## Prerequisites

### System Requirements

- **Linux/Ubuntu/Debian** (preferred) or Windows Subsystem for Linux (WSL)
- **Python 3.13+** or **Python 3.14**
- **PostgreSQL 16+** or **SQLite** (for development)
- **Redis 7+** (optional for production caching)
- **Node.js 18+** (for frontend build)

### Installation Commands

#### Ubuntu/Debian
```bash
# Install system dependencies
sudo apt update
sudo apt install -y python3-pip python3-venv postgresql postgresql-contrib redis-server nodejs npm

# Clone repository
git clone https://github.com/CHIKOJgg/aigenis-bond.git
cd aigenis-bond

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -e .

# Initialize database
# For SQLite: Environment is ready (conftest handles test DB)
# For PostgreSQL: See database setup below
```

#### Production Setup

```bash
# Create database user and database
sudo -u postgres createuser -s aigenis
sudo -u postgres createdb aigenis

# Set password for PostgreSQL
echo "ALTER USER aigenis WITH PASSWORD 'your_secure_password';" | sudo -u postgres psql

# Download and extract project
curl -L https://github.com/CHIKOJgg/aigenis-bond/archive/refs/heads/main.tar.gz -o project.tar.gz
tar -xf project.tar.gz
destructure aigenis-bond
destination/aigenis-parser
cd aigenis-parser

# Create virtual environment
python3 -m venv --prompt "aigenis" venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -e .

# Initialize database schemas
python3 -m alembic upgrade head
```

## Environment Configuration

Create a `.env` file in the project root with your credentials:

```env
# =============================================================================
# AIGENIS PARSER v3.0 SAAS - Production Configuration
# =============================================================================

# --- Database ---
DATABASE_URL=postgresql+asyncpg://aigenis:aigenis@postgres:5432/aigenis
DATABASE_URL_SYNC=postgresql://aigenis:aigenis@postgres:5432/aigenis

# --- Redis (optional) ---
REDIS_URL=redis://redis:6379/0

# --- JWT Authentication ---
JWT_SECRET_KEY=your_super_secret_jwt_key_here_at_least_32_chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# --- Google OAuth (optional) ---
# GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
# GOOGLE_CLIENT_SECRET=your_google_client_secret

# --- Stripe Payment (REQUIRED for production) ---
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here
# Plan configuration (can be overridden later)
STRIPE_PRICE_FREE=price_free_placeholder
STRIPE_PRICE_PRO=price_pro_placeholder
STRIPE_PRICE_ENTERPRISE=price_enterprise_placeholder

# --- Email Configuration (optional but recommended) ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=noreply@aigenis.by

# --- Admin Credentials (for admin panel access) ---
# These will be updated during setup
# ADMIN_EMAIL=admin@aigenis.by
# ADMIN_PASSWORD=strong_admin_password_here

# --- Application ---
AIGENIS_ENVIRONMENT=production
AIGENIS_LOG_LEVEL=INFO
AIGENIS_LOG_FILE=/var/log/aigenis/parser.log

# --- Server ---
API_PORT=8000
API_WORKERS=4
```

### Setting Up Admin Account

After creating the `.env` file, run this script to create the initial admin account:

```bash
cat << 'EOF' > setup_admin.py
import os
from sqlalchemy.future import create_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# Load environment
from dotenv import load_dotenv
load_dotenv()

from scraper.orm import Base

# Connect to database
engine = create_engine(os.getenv('DATABASE_URL_SYNC'))
SessionLocal = sessionmaker(bind=engine)

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Add admin user
with SessionLocal() as session:
    from scraper.orm import UserORM
    
    # Check if admin exists
    existing_admin = session.query(UserORM).filter(UserORM.email == os.getenv('ADMIN_EMAIL')).first()
    if existing_admin:
        print(f"Admin user already exists: {existing_admin.email}")
        exit(0)
    
    # Create admin user
    admin = UserORM(
        email=os.getenv('ADMIN_EMAIL'),
        name='System Administrator',
        password_hash='admin123456',  # You'll want to hash this properly
        role='admin',
        subscription_tier='enterprise',
        is_active=True,
        is_verified=True
    )
    session.add(admin)
    session.commit()
    print(f"✅ Admin user created: {admin.email} (ID: {admin.id})")
    print(f"⚠️  Please change the admin password and review security settings!")
EOF

python3 setup_admin.py
rm setup_admin.py
```

## Docker Deployment

### Option 1: Docker Compose (Recommended for Production)

Create `docker-compose.prod.yml`:

```yaml
docker-compose.prod.yml
version: '3.8'

networks:
  aigenis-net:
    name: aigenis-net
    driver: bridge

services:
  postgres:
    image: postgres:16-alpine
    container_name: aigenis-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-aigenis}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aigenis}
      POSTGRES_DB: ${POSTGRES_DB:-aigenis}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - aigenis-net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-aigenis} -d ${POSTGRES_DB:-aigenis}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s

  redis:
    image: redis:7-alpine
    container_name: aigenis-redis
    restart: unless-stopped
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    networks:
      - aigenis-net
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  api:
    build:
      context: .
      dockerfile: Dockerfile
    image: aigenis-api:latest
    container_name: aigenis-api
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      # Load from .env file
      - .env
    ports:
      - "${API_PORT:-8000}:8000"
    networks:
      - aigenis-net
    volumes:
      - ./logs:/var/log/aigenis
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: aigenis-frontend:latest
    container_name: aigenis-frontend
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - api
    environment:
      - NUXT_HOST=0.0.0.0
      - NUXT_PORT=80
      - API_BASE_URL=http://api:8000
    networks:
      - aigenis-net

volumes:
  pgdata:
    name: aigenis-pgdata
  redisdata:
    name: aigenis-redisdata
  logs:
    name: aigenis-logs
```

### Running with Docker Compose

```bash
# Build and start all services
cmake up-all  # Using Makefile from project

# Or with docker-compose directly
docker-compose -f docker-compose.prod.yml up -d

# Check logs
docker-compose -f docker-compose.prod.yml logs -f api

# Stop services
docker-compose -f docker-compose.prod.yml down
```

### Option 2: Individual Services

For development or specific services:

```bash
# API service only
docker compose -f docker-compose.yml --profile api up -d

# API with Redis (for testing)
docker compose -f docker-compose.yml --profile bot --profile api up -d

# Use Makefile shortcuts
make up-api        # Start API
make up-bot        # Start Bot + API
make up-all        # Start all services
```

## Frontend Configuration

### Local Development

```bash
# Frontend setup
cd frontend
npm install
npm run dev
```

### Build for Production

```bash
# Build frontend
cd frontend
npm run build

# Update nginx configuration or proxy
```

### Environment Variables for Frontend

```javascript
// frontend/vite.config.ts
const config = {
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
      '/api/v1': 'http://localhost:8000',
    }
  }
}
```

## Admin Panel Access

After deployment, access the admin panel:

1. **API Admin**: `http://your-server-ip:8000/admin`
2. **Frontend**: `http://your-server-ip:3000` (or configured port)

### Admin Login Credentials

Use the admin email and password you set up:

1. Navigate to `/admin/login` or `/admin` if already authenticated
2. Enter admin email and password
3. Use the token cookie for webhooks or programmatic access

## API Endpoints

### Public Endpoints

- `GET /health` - Health check
- `GET /ready` - Readiness probe
- `GET /api/v1/bonds` - List bonds
- `GET /api/v1/scores` - List bond scores
- `GET /api/v1/stats` - Platform statistics

### Authentication Endpoints

- `POST /auth/register` - Register new user
- `POST /auth/login` - Login user

## Monitoring and Logging

### Local Monitoring

```bash
# View logs
docker logs aigenis-api -f

# Check database
make psql

# Health checks
# - Frontend: http://your-server-ip:8000/api/v1/health
# - API: http://your-server-ip:8000/health
# - Admin: http://your-server-ip:8000/admin
```

### Production Monitoring

#### Log Files
- **API Logs**: `/var/log/aigenis/` on host
- **Database Logs**: PostgreSQL logs
- **Frontend Logs**: Container logs

#### Metrics
- Application metrics via `/metrics` (if enabled)
- Rate limiting logs
- Authentication logs
- API usage statistics

## Backup and Recovery

### Database Backup

```bash
# PostgreSQL backup
docker exec -it aigenis-postgres pg_dump -U aigenis aigenis > backup_$(date +\%Y\%m\%d).sql

# SQLite backup (development)
# cp data/bonds.db data/bonds_$(date +\%Y\%m\%d).db
```

### Application Backup

```bash
# Copy logs and configuration
tar -czf aigenis_backup_$(date +\%Y\%m\%d).tar.gz \config \logs
tar -xzf aigenis_backup_$(date +\%Y\%m\%d).tar.gz -C /new/server
```

## Security Configuration

### Recommended Security Settings

1. **HTTPS**: Use Let's Encrypt or commercial SSL certificates
2. **Firewall**: Configure firewall rules
3. **Rate Limiting**: API rate limiting is built-in
4. **CORS Configuration**: Configure appropriate CORS origins
5. **API Key Management**: Use environment variables, not hardcoded

### Secret Management

```bash
# Use environment variables and secrets management
# Never commit secrets to repository
echo "STRIPE_SECRET_KEY=prod-secret-key-123" >> .env
chmod 600 .env
```

## Updating the Application

### Simple Update Process

```bash
# Pull latest changes
git pull origin main

# Reinstall dependencies
pip install -e .

# Run migrations
python -m alembic upgrade head

# Restart services
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d

# Or using Makefile
make up-all
```

## Troubleshooting

### Common Issues

#### "FATAL: missing env vars"
Check that your `.env` file is properly configured and sourced.

#### "Permission denied"
Check file permissions and user access.

#### "Database connection failed"
Verify PostgreSQL credentials and service status.

#### "Stripe webhook errors"
Check your Stripe webhook secret key in the `.env` file.

#### "Admin login failed"
Verify admin credentials and user role.

### Debugging Commands

```bash
# Check database status
make status

# View API logs
make logs

# Check processes
ps aux | grep aigenis

# Check port usage
netstat -tulpn | grep 8000

# Restart services
make down
make up-all
```

## Support

For issues, please check:
1. GitHub repository: https://github.com/CHIKOJgg/aigenis-bond/issues
2. Configuration review
3. Log files for errors
4. Database state

## Acknowledgements

This deployment guide was created as part of the migration from version 2.0.0 to version 3.0.0, adding production-ready features including:

- JWT Authentication with Google OAuth support
- Stripe payment integration
- Admin panel with user management
- Feature tier-based access control
- Comprehensive logging and monitoring
- Docker/multi-environment deployment
- Security hardening

The project maintains backward compatibility while adding powerful SAAS features.