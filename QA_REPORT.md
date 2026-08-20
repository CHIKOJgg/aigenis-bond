# QA Report — Aigenis Bond Demo (aigenis-bond)

Date: 2026-08-18 · Environment: Docker (`aigenis-api` :8000, `aigenis-demo` :8080/demo, postgres, redis)
Scope: fix-all → full test chain → live manual QA of the demo at http://localhost:8080/demo

## Executive Summary

The demo application is **green across the entire verification chain** and the
**critical score-consistency defect found during QA is fixed and verified
end-to-end**. Backend tests pass (full suite), lint/format are clean, the
frontend passes lint/build/unit/e2e, and manual QA of every page found no
rendering or JS errors. One data-quality bug (stale stored scores) and one
consistency bug (list vs drawer scoring) were fixed; two minor UX/a11y items
remain and are listed below.

## Verification Chain (all green)

| Check | Result |
|---|---|
| Backend pytest (full suite) | PASS |
| ruff check / ruff format | PASS (0 errors; 348 files formatted) |
| mypy (informational, Makefile gate) | No regression vs baseline (45 vs 47) |
| Frontend oxlint | PASS |
| Frontend vitest | 143 tests PASS |
| Frontend `tsc -b && vite build` | PASS |
| Playwright e2e smoke | 33/33 PASS |
| Playwright e2e visual | 135/135 PASS |
| Playwright e2e perf | 8/8 PASS (LCP ≈ 400 ms) |
| `audit_demo.py` / `verify_demo_frontend.py` | PASS (fixtures consistent, strategy monotonicity) |
| `verify_prices.py` / `verify-calcs.py` | PASS (0 price/YTM mismatches in fixtures) |
| Security grep (secrets/keys) | CLEAN |
| Docker health | api 200 `{"status":"ok","db":"ok"}`, demo 200 |

## Fixed Issues (this session)

### 1. CRITICAL — Score inconsistency: market table vs bond drawer
**Symptoms:** same bond showed different scores — `/api/v1/demo/market-data`
(list/table) vs `/api/v1/demo/bond/{id}` (drawer). Example RCSD-00018:
table 19.22 vs drawer 44.23; breakdowns differed (yield_component 0 vs 8.99).

**Root causes (two):**
- **Stale `bond_scores`**: stored scores were computed 2026-08-07 while the
  bond feed was fetched 2026-08-17. The scheduled `scrape_daily` job (which
  runs `run_once` → `recompute_all`) has no `job_runs` records in this
  environment; the feed was ingested through a bootstrap path that updated
  bonds without recomputing scores. 340/343 bonds mismatched.
- **Scoring divergence**: `scoring/repository.py::_validate_stored_ytm` kept
  the feed-supplied YTM whenever it was within the 2 pp `sane_yield`
  tolerance of the price-implied YTM, while the detail endpoint
  `api/demo.py::_bond_analytics` always recomputes YTM from the live price.
  Result: 8 bonds with material stored-vs-live score differences (e.g.
  5-200-02-5153: 38.38 vs 37.2; 5-200-02-4363: 61.0 vs 48.21).

**Fixes:**
- `scoring/repository.py`: `_validate_stored_ytm` now always prefers the
  price-implied YTM when a positive estimate is computable (matches the
  documented intent of `_bond_analytics`: "always recompute from the actual
  market price, not the possibly stale stored value").
- `api/demo.py`: `_fast_bond_payload` no longer serves a stored score for
  **matured bonds** (`maturity_date < today`) — the detail endpoint already
  returns "no analytics" for them (7-401-02-5220: list 35.48 vs drawer none).
- Re-ran `recompute_all` (1509 bonds) against the live DB.

**Verification:** 343/343 BCSE bonds and a 12/12 MOEX sample now return
identical score + breakdown from both endpoints (0 mismatches, 0 errors).
Browser check: table row and drawer both show "44 Score" for RCSD-00018.

### 2. Ruff quality gate (from previous pass, re-verified)
`scraper/orm/bonds.py` (unused arg), `scoring/repository.py` and
`portfolio/optimizer.py` (C901 complexity) refactored; all checks green.

## Financial Discrepancies vs Real Market Data

- Live BCSE (343) / MOEX (688) quotes come from the licensed feed with
  `fetched_at` 2026-08-17 19:09 UTC; `as_of` stamp is shown in the UI
  ("актуально на 17.08.2026, 19:09:46") — no discrepancy.
- Price/YTM consistency re-verified on fixtures (verify_prices: 0 mismatches);
  live price/YTM pairs are internally consistent by construction (YTM is
  solved from price and stored back).
- Zero-coupon bonds show honest "—" YTM where unsolvable (e.g. ЛяховичиРИК
  Оп3), and matured bond 7-401-02-5220 correctly shows no analytics.

## Bug & Edge Case Log

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | Critical | Stored scores stale vs live data; list/drawer score mismatch | **Fixed & verified (343/343)** |
| 2 | Medium | Matured bond still scored in the list | **Fixed** |
| 3 | Minor | "Уведомления" / "Настройки" buttons in DemoTopBar have no `onClick` — pointer cursor, zero feedback | Open — recommend demo toast or wiring |
| 4 | Minor | a11y: form fields without `label`/`id`/`name` (analytics/optimizer) | Open — recommend labels + ids |
| 5 | Info | Market-data response is TTL-cached (300 s) — after a score recompute the list can lag up to 5 min | By design, documented in code |
| 6 | Info | Detail endpoint rate-limited (60 req/min/IP, global middleware) — a 343-request audit tripped 429s (earlier misread as 404 "not found" — verified false) | Not a defect for normal UI use |
| 7 | Info | `scrape_daily` scheduler job had no run records; scores had to be refreshed manually via `scraper score` | Recommend: ensure every feed ingest runs `recompute_all` (pipeline already does in `run_once`/backfill paths) |

## Manual QA Summary (live demo)

- **Торги**: 343 BCSE / 688 MOEX; market filter works; drawer score == table
  score; search box in header works.
- **Аналитика**: dashboard renders (322 bonds, 24.39% avg yield); single API
  call, 200.
- **Desk (Кривые)**: Nelson-Siegel curves per currency (BYN/USD/RUB/EUR);
  Z-score anomaly signals with explanations (e.g. Оливер Оп9 BUY, Z=+4.87).
- **Стресс-тесты**: scenario selection + full per-bond P&L table; credit
  shock (+150 b.p.) yields plausible negative P&L; duration shift shown.
- **Робо-Оптимизатор**: Markovitz/Risk-Parity; Sharpe/Sortino/MDD; strategy
  selection (7 strategies incl. Carry Trade, Долларизация, Металлы++);
  allocation table with per-bond YTM.
- **Лаборатория портфелей**: persona portfolio with return 14.26%, Sharpe
  13.37, VaR 95% 1.26%, Sortino 19.11, Calmar 12.39; per-position table.
- **Поиск**: live search by name/ISIN (query "минфин" → 4 MOEX bonds with
  scores); empty query handled gracefully.
- **Mobile (390 px)**: no horizontal overflow; hamburger menu present.
- **Console**: zero JS errors across all pages; 2 a11y issues only (item 4).

## Recommendations

1. Wire the scheduled `scrape_daily` run (or add a post-ingest hook) so
   `bond_scores` are recomputed automatically after every feed update —
   prevents recurrence of the stale-score defect.
2. Give "Уведомления"/"Настройки" a demo response (toast: "недоступно в
   демо") or remove the pointer cursor until wired.
3. Add `label`/`id` attributes to form controls flagged by the browser.
4. (Optional) Consider lowering `_MARKET_CACHE_TTL` or versioning the cache
   key by max `computed_at` so refreshed scores surface faster.