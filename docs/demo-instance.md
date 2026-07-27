# Deployment Guide — Demo Instance Bonds Engine

## Quick start (1 command, $0)

```bash
# 1. Clone repo
git clone https://github.com/CHIKOJgg/bonds-engine.git
cd bonds-engine

# 2. Setup env for demo mode
cp .env.example .env
# In .env make sure:
#   DATA_SOURCE=moex
#   DEMO_MODE=1
#   SEO_PUBLIC_BASE_URL=https://demo.yourdomain.com

# 3. Run demo stack (no paid source needed)
docker compose up -d postgres redis parser api frontend

# 4. Run MOEX data fetch (public, no auth)
docker compose run --rm parser moex --currency RUB,USD,EUR

# 5. Health check
curl -f http://localhost/health
```

## Public demo with Cloudflare Tunnel (optional)

```bash
# Option A: Quick tunnel (no token, temporary URL)
docker compose --profile quick-tunnel up -d cloudflared-quick
docker compose logs -f cloudflared-quick  # find the URL

# Option B: Production tunnel
# Set CLOUDFLARED_TUNNEL_TOKEN in .env, then:
docker compose --profile tunnel up -d cloudflared
```

The URL returned by Cloudflare will be your public demo:
`https://<something>.trycloudflare.com`

## Demo features (no auth, read-only, watermark)

All public routes work without login when DEMO_MODE=1:
- `/bonds` — bond leaderboard
- `/bonds/{internal_id}` — individual bond detail
- `/partners` — self-serve API key issuance form
- `/widget/top` — top bonds embed endpoint
- `/calculator` — YTM calculator
- `/guides/*` — educational articles

## What you will see

1. Top bonds by Score with currency filter
2. Click any bond → full detail (Score, YTM, coupon, maturity)
3. Click "Get API Key" on /partners → test key issued in Telegram (if bot configured) or shown on screen
4. Widget at /widget → iframe embeddable on any site
5. Pricing page with currency auto-detection (BYN for BY IP, RUB for RU, USD for others)

## Notes

- No paid source login required (MOEX ISS is public)
- No Telegram bot needed for demo (bot commands won't work, but web UI is complete)
- No YooKassa needed (paywall returns 402 upgrade hint)
- All data is real (from MOEX ISS API)
