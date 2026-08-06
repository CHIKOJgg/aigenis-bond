# Threat Model — Aigenis Analytics Integration

**Date:** 2026-08-06
**Scope:** Analytics module delivered to Aigenis terminal

## Threat 1: Unauthorized API access (T-001)

| Field | Detail |
|-------|--------|
| **Risk** | External actor calls Analytics API without valid Aigenis SSO token |
| **Impact** | Data leak, unauthorized scoring access |
| **Mitigation** | SSO JWT validation (iss, aud, exp, signature via JWKS). CORS allowlist for Aigenis origins only. All endpoints require Bearer token. |
| **Status** | Implemented in api/aigenis — verify_sso_token dependency |

## Threat 2: iframe embedding attack (T-002)

| Field | Detail |
|-------|--------|
| **Risk** | Third-party site embeds analytics iframe, captures user interactions |
| **Impact** | Clickjacking, phishing of Aigenis users |
| **Mitigation** | `frame-ancestors` CSP header set to Aigenis domain only. No long-lived JWT in URL. postMessage validated by origin + schema. |
| **Status** | To be implemented in nginx.aigenis.conf |

## Threat 3: Data exfiltration (T-003)

| Field | Detail |
|-------|--------|
| **Risk** | Unauthorized party extracts bulk bond data or portfolio structures |
| **Impact** | Data licensing breach, competitive intelligence loss |
| **Mitigation** | Rate limiting per user/IP. Pagination caps (max 100 per page). No bulk export endpoint. Audit log of all data access. |
| **Status** | Rate limiting: Redis-based. Pagination: cursor-based. Audit: structured logs. |

## Threat 4: Order flow injection (T-004)

| Field | Detail |
|-------|--------|
| **Risk** | Malicious actor modifies order deep-link to inject fake trades |
| **Impact** | Unauthorized order creation, regulatory breach |
| **Mitigation** | Analytics ONLY passes instrument_id + source=analytics to Aigenis order flow. No quantity/price/portfolio data in URL. Order confirmation happens in Aigenis terminal (not analytics). |
| **Status** | Design enforced — analytics is decision support, not order management. |

## Threat 5: Webhook replay (T-005)

| Field | Detail |
|-------|--------|
| **Risk** | Attacker replays alert notifications to manipulate users |
| **Impact** | False alerts, user confusion |
| **Mitigation** | Signed webhook payloads (HMAC). Idempotency-Key for alert creation. Replay detection via audit log. |
| **Status** | Idempotency-Key in AlertRequest. HMAC signing to be added in production. |

## Threat 6: Token theft via localStorage (T-006)

| Field | Detail |
|-------|--------|
| **Risk** | XSS attack steals access/refresh tokens from localStorage |
| **Impact** | Account takeover in Aigenis terminal |
| **Mitigation** | BFF pattern: browser receives HttpOnly; Secure; SameSite session cookie. Analytics module never stores tokens in localStorage. Gateway transforms cookie → service token. |
| **Status** | BFF pattern documented. Implementation pending Aigenis SSO integration. |

## Threat 7: Browser scraping in production (T-007)

| Field | Detail |
|-------|--------|
| **Risk** | Production uses browser scraping instead of official data feed |
| **Impact** | Data licensing breach, legal liability |
| **Mitigation** | `DEPLOYMENT_PROFILE=aigenis` disables browser scraping (fail-closed). Only official MarketDataProvider allowed in production. |
| **Status** | Implemented via AIGENIS_HEADLESS=false in docker-compose.aigenis.yml. |
