# Aigenis Live Demo Runbook

## Purpose

This is the verified proof-of-value route for Aigenis. It demonstrates the
actual data and analytics pipeline, not a static product mockup:

`Aigenis source -> PostgreSQL -> scoring/analytics engine -> FastAPI demo API -> React UI`

Demo URL: `http://localhost:8080/demo`

## Runtime Contract

The demo uses live, read-only endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/demo/market-data?market=bcse` | Live market universe, YTM, duration, Score and data timestamp |
| `GET /api/v1/demo/market-data?market=moex` | MOEX live market universe |
| `GET /api/v1/demo/search?q=...` | Live search by name, issuer, ISIN or internal ID |
| `GET /api/v1/demo/bond/{internal_id}` | Live detail, Score breakdown, explainability, history and coupon schedule |

The UI must not replace failed live responses with fixture data. A source
failure is shown as an explicit error/loading state. The demo does not expose
orders, payments, auth, alerts or write endpoints.

## Presentation Route

1. Open `http://localhost:8080/demo/trading` and confirm the live source and timestamp.
2. Switch between BCSE and MOEX to show the connected market universe.
3. Open `Аналитика`, select market/currency/term/status and sort by `Score` or `YTM`.
4. Use the live `Score/YTM` chart to explain the trade-off between return and risk.
5. Choose a current instrument with a meaningful Score and open its detail drawer.
6. Show Score, tier, YTM, duration, price, breakdown and `Почему такой рейтинг`.
7. Expand `Как считается Score` and show the reward/risk model in plain language.
8. Show live history/coupon schedule when the source provides them.
9. Click `Влияние на портфель`.
10. Select 10% of Marina's `50 000 BYN` portfolio, equal to `5 000 BYN`.
11. Show before/after graph for yield and duration, then live Score, YTM, annual income, data freshness, liquidity and risk-profile fit.
12. Show `Риск эмитента`: engine-derived score, level and basis. Compare issuers only when the live source provides comparable data.
13. Use the Portfolio Impact combobox to find another live paper by name, issuer or ISIN.
14. Click `Купить` to show the prepared order context. The demo does not submit an order; production wiring passes the instrument context into Aigenis' order ticket.
15. Close with the Aigenis pilot: catalog, bond detail and Portfolio Impact integrated with their source.

## Verification Commands

```bash
docker compose up -d postgres redis parser api
docker compose -f docker-compose.demo.yml up -d --build
docker compose -f docker-compose.demo.yml ps
curl -f http://localhost:8080/health
curl -f "http://localhost:8080/api/v1/demo/market-data?market=bcse&limit=5"
```

The market response must include `source`, `as_of`, `bonds`, `score`,
`score_status`, `breakdown`, `issuer_risk` and `disclaimer`.

`issuer_risk` is an explainable internal risk view derived from issuer
classification, the scoring engine's `credit_risk_component` and issue status.
It is not a rating agency opinion. Do not claim that one named company is more
reliable than another unless the source includes validated financial or rating
data supporting that comparison.

## Failure Handling

- `502` or empty market: check `api` health and that both containers share `aigenis-net`.
- Stale `as_of`: check parser/scheduler and source freshness before presenting.
- No Score: choose another current instrument or explain that the source row has insufficient scoring inputs.
- Detail `404`: return to the live table and open an instrument from the current response.
- Live API unavailable: do not claim that the screen is showing current market data.
