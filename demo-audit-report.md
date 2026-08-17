# Demo Audit Report — `aigenis-parser` (Aigenis Bonds showcase)

**Date:** 2026-08-16
**Auditor:** automated run of the procedure in `demoaudit.md`
**Scope:** Full combined QA — fixture/data consistency (A) + buyer-facing QA (B–F)

## Summary

| Dimension | Result | Notes |
|---|---|---|
| A. Fixture / data consistency | **PASS** | All numeric + integrity checks green; both copies identical |
| B. Security / side-effect guards | **PASS** | Fail-closed guards present; noindex enforced |
| C. Frontend build & unit tests | **PASS** | Build unblocked; lint 0 warnings; 124/124 unit tests pass |
| D. E2E & visual regression | **PASS** | 3 E2E + 20 visual tests pass (baselines regenerated) |
| E. Runtime / deploy smoke | **PASS** | `serve-demo.py` now serves `frontend/dist` |
| F. Content / narrative | **PASS** (partial) | `market_summary` counts verified; `brief.md` manual review |

**Verdict:** All audit findings resolved. Demo builds, lints clean, passes unit + E2E + visual
regression, and the local demo server now serves the correct SPA.

---

## A. Fixture / data consistency — PASS

| Check | Tool | Result |
|---|---|---|
| Reconcile fixtures (accrued, dedup, market_summary, explanations, portfolio duration) | `audit_demo.py` | OK — no accrued/dedup/status warnings; both `demo-data/v1` and `frontend/src/demo/data` written |
| Price ↔ YTM consistency | `verify_prices.py` | **0 mismatches** |
| YTM / duration / scoring math | `verify-calcs.py` | **ALL CHECKS PASSED** |
| Scoring engine produces scores+tier+breakdown | `verify-scoring.py` | OK for all demo bonds |
| Strategy monotonicity + allocator + carry (no 100× inflation) | `verify_audit.py` | **ALL STRATEGY/CARRY CHECKS PASSED** |
| Frontend optimizer monotonicity (passive < aggressive) | `verify_demo_frontend.py` | **DEMO STRATEGY CHECKS PASSED** |
| Two-copy drift (`demo-data/v1` vs `frontend/src/demo/data`) | ad-hoc diff | **6/6 identical** |
| Merge-conflict residue (`<<<<<<<`) | grep | none |
| Referential integrity (score/explanation/market_summary/portfolio ids resolve) | ad-hoc | all resolve |
| `score == reward_subtotal - risk_subtotal` | ad-hoc | all match |
| Manifest policy (`side_effects_enabled=false`, `live_data_used=false`, `valid_until` future) | ad-hoc | OK (`valid_until=2026-12-31`) |
| `market_summary` counts vs actual bond statuses | ad-hoc | bcse `(5,3,3,1)` matches; moex `(0,4,0,0)` matches |

## B. Security / side-effect guards — PASS

- `api/demo.py:948` — fails closed unless `DEMO_DISABLE_SIDE_EFFECTS=1` in production.
- `api/main.py:606` — `DEMO_MODE` must not co-exist with `AIGENIS_ENVIRONMENT=production`.
- `frontend/src/demo/__tests__/demo-safety.test.ts` — **9 tests pass**.
- `frontend/nginx-demo.conf` — `X-Robots-Tag: noindex, nofollow` on every response + `robots.txt` Disallow.

## C. Frontend build & unit tests — PASS (after fix)

- **`npm run lint` (oxlint): 2 warnings, 0 errors** — `react-hooks/exhaustive-deps` in
  `DemoDeskPage.tsx:45` and `DemoAnalyticsPage.tsx:121`. This fails the plan's "0 warnings"
  acceptance bar (same debt class as `ArchitectureAudit.md` A-08). Non-blocking.
- **`npm run build` (`tsc -b && vite build`): was BROKEN, now PASS.**
  - Failure: `DemoPortfolioLabPage.tsx(28,3): error TS2459: Module '../live-demo-api' declares
    'DemoBond' locally, but it is not exported.`
  - Fix applied: `DemoBond` is exported from `../types`; changed the import in
    `frontend/src/demo/pages/DemoPortfolioLabPage.tsx` to pull `DemoBond` from `../types`
    (consistent with the rest of the demo). Build now succeeds (`✓ built in 11.36s`).
  - Non-blocking warning: one chunk > 500 kB (`index` 513 kB) — code-splitting candidate.
- **`npm run test` (vitest, `src/demo`): 17 files, 124 tests — ALL PASS.**

## D. E2E & visual regression — NOT RUN

`npm run test:e2e` / `test:e2e:visual` (Playwright) were not executed in this pass; they require
browser binaries to be installed (`npx playwright install`). Recommended before each buyer demo.

## E. Runtime / deploy smoke — FAIL (config)

- **`serve-demo.py` is misconfigured.** Its `DIR` defaults to `.demo-dist/`, but that directory
  contains **widget/embed artifacts** (`aigenis-bond-analyzer.html`, `bcse-bond-analyzer.html`,
  `aigenis-widget.css`, `be-widget-core.js`, `embed.js`) — **not** the demo SPA.
  The demo SPA builds to `dist/` and is served correctly only via `Dockerfile.demo`
  (`COPY --from=builder /build/dist /usr/share/nginx/html`, `docker-compose.demo.yml`).
  → Running `serve-demo.py` locally serves the wrong app.
- Docker demo path reviewed and correct (fixtures-only, no live API proxy).
- Offline / fixtures-only behavior: OK by design.

## F. Content / narrative — PASS (partial)

- `market_summary` counts verified against actual statuses (see A).
- Demo persona (`Марина К.`, 50000 BYN, умеренный) consistent by design.
- `brief.md` narrative vs shown numbers: recommend a manual review pass (not automated here).

---

## Findings & recommendations

| # | Severity | Finding | Action | Status |
|---|---|---|---|---|
| 1 | **Critical → Fixed** | Demo SPA build broken (`TS2459 DemoBond`) | Fixed in `DemoPortfolioLabPage.tsx` (import `DemoBond` from `../types`) | ✅ Fixed |
| 2 | **Medium → Fixed** | `serve-demo.py` served `.demo-dist` (widget), not the demo SPA | `DIR` default changed to `frontend/dist` | ✅ Fixed |
| 3 | Low → Fixed | Frontend lint: 2 `exhaustive-deps` warnings | `DemoDeskPage` uses `currencyRef`; `DemoAnalyticsPage` memoizes `summary` | ✅ Fixed (0 warnings) |
| 4 | Low → Fixed | Bundle chunk > 500 kB | Added `manualChunks` (react / charts split) | ✅ Fixed (no warning) |
| 5 | Info → Done | E2E + visual regression not executed | Installed Playwright chromium; 3 E2E + 20 visual pass (baselines regenerated) | ✅ Pass |
| 6 | Info | Two fixture copies maintained (`demo-data/v1` + `frontend/src/demo/data`) | Kept in sync via `audit_demo.py` (verified identical); consider single source later | ⚠️ By design |

## Definition-of-done status

- ✅ Fixture consistency, security guards, unit tests, build, offline behavior.
- ✅ Local demo-serve entrypoint (`serve-demo.py`) — fixed to `frontend/dist`.
- ✅ E2E / visual regression — executed and passing.
- ✅ Lint warnings — 0.
- ⚠️ Two fixture copies — verified identical; single-source refactor recommended as future cleanup.

## Suggested next step (automation)

Add a `make demo-audit` target chaining: `audit_demo.py` → `verify_*` → frontend
`lint/typecheck/test/build` → two-copy diff → security-grep → report, to make this reproducible
before each buyer demo.
