# Operations Guide — Bonds Engine v4

## Monitoring

### Built-in Health Checks

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health + DB connectivity |
| `GET /ready` | Readiness probe (all dependencies) |
| `GET /metrics` | Prometheus metrics (per service) |

### Docker Health Checks

All services have Docker health checks configured:

```bash
# Check health status
docker compose ps

# Follow health check logs
docker compose logs -f api
```

### Prometheus + Grafana

- **Prometheus**: `http://localhost:9090` (localhost only)
- **Grafana**: `http://localhost:3001` (localhost only)
  - Default credentials: admin / (set via `GRAFANA_ADMIN_PASSWORD`)

Key Grafana dashboards:
1. **API Metrics** — request rate, latency, error rate
2. **Scraper Metrics** — bonds collected, parse errors, backfill progress
3. **ML Metrics** — model MAE, training status, prediction volume
4. **System Metrics** — CPU, memory, disk, network per container

## Logging

### Log Levels

| Level | Use Case |
|---|---|
| `DEBUG` | Development troubleshooting |
| `INFO` | Normal operations (default) |
| `WARNING` | Non-critical issues |
| `ERROR` | Failed operations |
| `CRITICAL` | Service-affecting failures |

Set via `AIGENIS_LOG_LEVEL` environment variable.

### Log Format

JSON format in production (`AIGENIS_LOG_JSON=true`):

```json
{
  "timestamp": "2026-08-02T09:45:37Z",
  "level": "INFO",
  "service": "api",
  "message": "Request processed",
  "duration_ms": 45,
  "user_id": "uuid"
}
```

### Log Rotation

- Max file size: 100 MB (`AIGENIS_LOG_ROTATION`)
- Retention: 14 days (`AIGENIS_LOG_RETENTION`)
- Logs stored in `logs/` volume (persists across restarts)

## Alerting

### Telegram Alerts

The bot can send alerts to configured chat IDs:
- Bond price changes exceeding threshold
- ML model degradation (MAE increase)
- Scraper failures
- Database connection issues

Configure via `TELEGRAM_ALERT_CHAT_ID` in `.env`.

### Prometheus Alerting Rules

Defined in `docker/prometheus/prometheus.yml`:
- High error rate (>5% over 5m)
- High latency (p99 > 1s over 5m)
- Service down (health check fails)
- Database connection pool exhaustion

## Backup & Recovery

### Database Backup

```bash
# Manual backup
docker compose exec postgres pg_dump -U aigenis aigenis > backup_$(date +%Y%m%d).sql

# Restore
docker compose exec -T postgres psql -U aigenis -d aigenis < backup.sql
```

### Volume Backup

```bash
# Backup all Docker volumes
docker run --rm -v aigenis-pgdata:/data -v $(pwd):/backup alpine tar czf /backup/pgdata-backup.tar.gz -C /data .
```

### Backup Schedule

Recommended: daily automated backup using a cron job or a scheduled Docker Compose service.

## Scaling

### Horizontal (API)

```bash
# Scale API workers
docker compose up -d --scale api=3
```

### Vertical (Resources)

Adjust `.env` resource limits:
```
API_MEM_LIMIT=1G
API_MEM_RESERVE=512M
```

### Database Connection Pooling

For high concurrency:
```
DB_POOL_SIZE=20
DB_POOL_OVERFLOW=40
```

## Troubleshooting

### Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| API 500 on `/health` | DB not ready | Wait for postgres health check |
| Bot not responding | Invalid `TELEGRAM_BOT_TOKEN` | Verify token with @BotFather |
| Scraper stuck | MOEX rate limit | Increase `MOEX_TIMEOUT` or reduce `MOEX_CAP` |
| High memory usage | Large backfill job | Reduce `AIGENIS_HISTORY_BACKFILL_DAYS` |
| WebSocket disconnects | Nginx timeout | Increase `proxy_read_timeout` |
| SSL certificate expired | Certbot not renewing | Run `docker compose --profile certbot run --rm certbot renew` |
| Tunnel not connecting | Port 7844 blocked | Use named tunnel instead of quick tunnel |

### Debug Commands

```bash
# Check all service logs
docker compose logs --tail=100

# Check specific service
docker compose logs -f api

# Run a one-off command
docker compose exec api python -c "from scraper.db import session_scope; print('DB OK')"

# Inspect database
docker compose exec postgres psql -U aigenis -d aigenis -c "SELECT count(*) FROM bonds;"

# Check Redis
docker compose exec redis redis-cli ping

# Check network
docker network inspect aigenis-net
```

## Maintenance

### Database Migrations

```bash
# Apply pending migrations
docker compose exec api alembic upgrade head

# Create a new migration
docker compose exec api alembic revision --autogenerate -m "description"
```

### Updating the Application

```bash
# Pull latest code
git pull

# Rebuild images
docker compose build

# Apply migrations
docker compose exec api alembic upgrade head

# Restart
docker compose up -d
```

### Cleaning Up

```bash
# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Full reset (destroys all data!)
docker compose down -v --rmi all
```