# Demo Audit Plan — `aigenis-parser` (Aigenis Bonds showcase)

## 1. Purpose & scope

The "demo" is the buyer-facing showcase of the Aigenis Bonds product. It is a
**fixtures-only, read-only** build: static JSON in `demo-data/v1/` and
`frontend/src/demo/data/`, a React demo SPA (`frontend/src/demo/`), and a guarded
backend blueprint (`api/demo.py`) behind `DEMO_DISABLE_SIDE_EFFECTS` /
`DEMO_MODE` flags. It can be served by `serve-demo.py` (local) or
`docker-compose.demo.yml` + `Dockerfile.demo` (nginx, `.demo-dist`).

This plan audits it end-to-end before presenting to Aigenis, combining:

- **(A) Fixture/data consistency** — extend `audit_demo.py` + the existing
  `verify_*.py` scripts.
- **(B) Buyer-facing QA** — frontend build/tests, E2E, visual regression,
  security/side-effect guards, deploy smoke.

## 2. Audit target inventory

| Layer | Paths |
|---|---|
| Fixtures (backend) | `demo-data/v1/{bonds_bcse,bonds_moex,scores,explanations,market_summary,portfolio_templates}.json`, `demo-data/v1/brief.md`, `demo-data/{manifest,v1/manifest}.json` |
| Fixtures (frontend copy) | `frontend/src/demo/data/*.json` |
| Backend demo API | `api/demo.py`, `api/main.py` (DEMO_MODE fail-closed), `api/access_control.py` (is_demo) |
| Frontend demo app | `frontend/src/demo/` (DemoShell, pages, components, `__tests__/`) |
| Build/deploy | `frontend/Dockerfile.demo`, `frontend/nginx-demo.conf`, `docker-compose.demo.yml`, `docker-compose.demo-tunnel.yml`, `serve-demo.py`, `.demo-dist/` |
| Existing audit tooling | `audit_demo.py`, `verify_audit.py`, `verify_demo_frontend.py`, `verify_prices.py`, `verify-calcs.py`, `verify-scoring.py`, `verify-scoring-real.py` |

## 3. Audit dimensions & checks

### A. Fixture / data consistency

- **Referential integrity:** every `scores.*.internal_id`,
  `explanations.*.internal_id`, `portfolio_templates` position `instrument_id`,
  and `market_summary` best-yield id must exist in `bonds_bcse`/`bonds_moex`.
  `manifest.demo_bonds` must equal the actual bond set.
- **Numeric invariants (reuse existing scripts):**
  - `accrued_interest` recompute (via `desk.cashflow`) ≈ stored (`audit_demo.py`).
  - Price ↔ YTM consistency (`verify_prices.py`).
  - YTM / duration / scoring math (`verify-calcs.py`, `verify-scoring.py`).
  - Strategy monotonicity, allocator sanity, carry trade (no 100× inflation)
    (`verify_audit.py`, `verify_demo_frontend.py`).
  - `score == reward_subtotal - risk_subtotal`; tier↔status↔verdict alignment;
    portfolio benchmark `duration_years` == weighted modified duration
    (`desk.duration`).
- **Merge-conflict residue:** no `<<<<<<<` / `>>>>>>>` markers in any demo JSON
  (the `audit_demo.py` resolver must have fully cleaned them).
- **Two-copy drift:** `demo-data/v1/*.json` and `frontend/src/demo/data/*.json`
  must be byte-identical (both are written by `audit_demo.py` DATA_DIRS — add an
  explicit `diff` gate).
- **Manifest policy:** `side_effects_enabled=false`, `live_data_used=false`,
  `valid_until` in the future.

### B. Security / side-effect guards

- `api/demo.py:948` must fail closed unless `DEMO_DISABLE_SIDE_EFFECTS=1` in
  production.
- `api/main.py:606` DEMO_MODE must not co-exist with `AIGENIS_ENV=production`.
- All write/POST endpoints unreachable in demo; `X-Is-Demo: true` header present.
- `frontend/src/demo/__tests__/demo-safety.test.ts` must pass.
- `.env` / `.env.aigenis.example` contain no real secrets;
  `CLOUDFLARED_TUNNEL_TOKEN` never committed.
- `nginx-demo.conf` enforces `X-Robots-Tag: noindex` + `robots.txt` Disallow.

### C. Frontend build & unit tests

- `npm ci`, `npm run lint` → 0 warnings, `npm run typecheck` (tsc) clean.
- `npm run test` (Vitest) — full `frontend/src/demo/__tests__/` green, incl.
  no-data/empty states.
- `npm run build` → produces `.demo-dist` (fixtures-only, no live API).

### D. End-to-end & visual regression

- Playwright flow: Analytics → Search → Bond detail drawer → Optimizer →
  Portfolio Impact → Desk → Stress.
- Visual-regression baseline screenshots (light/dark, key pages).
- Explicit checks for error / empty / stale-data states (already covered by
  `bond-detail-drawer-nodata.test.tsx`).

### E. Runtime / deploy smoke

- `python serve-demo.py` serves `.demo-dist` with SPA fallback (local).
- `docker compose -f docker-compose.demo.yml up -d --build` → container healthy
  (`/health`).
- Confirm no outbound API dependency (fixtures-only): app works offline.
- Optional tunnel: `docker-compose.demo-tunnel.yml` only with env token, targets
  `:8080`.

### F. Content / narrative correctness

- `brief.md` numbers match shown data; disclaimer + watermark present.
- `market_summary` counts (attractive/needs_review/neutral/high_risk) match
  actual bond statuses.
- Demo persona (`Марина К.`, 50000 BYN, умеренный) consistent across UI +
  portfolio templates.

## 4. Audit runbook (ordered)

1. **Prereqs:** activate `.venv`, `cd frontend && npm ci`.
2. **Reconcile fixtures:** `.venv/Scripts/python.exe audit_demo.py`.
3. **Numeric verification:** run `verify_prices.py`, `verify-calcs.py`,
   `verify-scoring.py`, `verify_audit.py`, `verify_demo_frontend.py` — all green.
4. **Two-copy diff:** `diff demo-data/v1 frontend/src/demo/data` (only JSON) →
   identical.
5. **Frontend:** `npm run lint && npm run typecheck && npm run test &&
   npm run build`.
6. **E2E + visual:** `npm run test:e2e` + `npm run test:e2e:visual` (Playwright
   installed).
7. **Security gates:** grep asserts `DEMO_DISABLE_SIDE_EFFECTS`/`DEMO_MODE`
   guards; run `demo-safety.test.ts`; confirm env files have no secrets.
8. **Deploy smoke:** build/run `docker-compose.demo.yml`, `curl /health`, load
   `/` and walk 2 pages.
9. **Report:** emit `demo-audit-report.md` with a pass/fail table per check
   above.

## 5. Acceptance criteria (definition of done)

- All (A)–(F) checks green; zero `<<<<<<<` markers; two fixture copies identical;
  lint 0 warnings; typecheck clean; demo unit + E2E + visual green; security
  fail-closed guards confirmed; demo serves offline; report artifact produced.

## 6. Proposed automation

Add a `make demo-audit` target chaining steps 2–8 and generating the report, so
the audit is reproducible before each buyer demo (mirrors existing `make verify`).

## 7. Risks & known gaps

- **Two fixture copies** (`demo-data/v1` + `frontend/src/demo/data`) is fragile
  — recommend a single source of truth to remove drift risk.
- `api/demo.py` is large (~85 KB) — regressions easy to miss; keep
  `demo-safety.test.ts` + contract checks.
- Demo `valid_until` (2026-08-13 in root manifest) — needs a refresh/expiry
  policy before each presentation.

## 8. Next steps (after approval)

1. Write this plan to `DEMO_AUDIT_PLAN.md`.
2. Wire a `make demo-audit` target and a `scripts/demo_audit_report.py` to
   automate steps 2–9.
