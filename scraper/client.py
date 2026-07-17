from __future__ import annotations

import asyncio
import random
import sys
import time
from contextlib import asynccontextmanager, suppress
from datetime import date
from typing import Any

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright_stealth import Stealth
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.config import Settings, get_settings
from scraper.errors import (
    BrowserNotAvailable,
    CircuitBreakerOpenError,
    FatalError,
    NotFoundError,
    ParseError,
    TransientError,
)
from scraper.logging import get_logger

logger = get_logger("scraper.client")

API_BASE = "https://invest.aigenis.by/api"
SITE_BASE = "https://invest.aigenis.by"


def _abs_url(url: str | None) -> str | None:
    """Make a relative issuer logo URL absolute against the aigenis.by site."""
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return SITE_BASE + url
    return SITE_BASE + "/" + url


class _CircuitBreaker:
    """Simple circuit breaker for browser operations."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures = 0
        self._last_failure_time = 0.0
        self._state = "closed"

    @property
    def state(self) -> str:
        if (
            self._state == "open"
            and (time.monotonic() - self._last_failure_time) > self._recovery_timeout
        ):
            self._state = "half-open"
        return self._state

    def record_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._failures += 1
        self._last_failure_time = time.monotonic()
        if self._failures >= self._failure_threshold:
            self._state = "open"
            logger.error("circuit_breaker_opened", failures=self._failures)

    async def __aenter__(self):
        if self.state == "open":
            raise CircuitBreakerOpenError("Browser circuit breaker is open")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type and issubclass(exc_type, (TransientError, PlaywrightTimeoutError)):
            self.record_failure()
        else:
            self.record_success()


class AigenisClient:
    """HTTP/Playwright client for Aigenis with circuit breaker and health checks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings().aigenis
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._stealth = Stealth() if self.settings.use_stealth else None
        self._html_cache: dict[str, asyncio.Future[str]] = {}
        self._html_cache_lock = asyncio.Lock()
        self._circuit_breaker = _CircuitBreaker()
        self._last_health_check = 0.0
        self._started = False
        self._token: str | None = None
        self._token_expires: float = 0.0
        self._auth_lock = asyncio.Lock()
        self._id_by_internal: dict[str, int] = {}
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> AigenisClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._started:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.settings.user_agent,
            locale="ru-RU",
            timezone_id="Europe/Minsk",
            ignore_https_errors=self.settings.ignore_https_errors,
        )
        if self._stealth is not None:
            try:
                await self._stealth.apply_context(self._context)
            except Exception:
                logger.warning("stealth_apply_failed")
        self._started = True
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout),
            headers={"User-Agent": self.settings.user_agent},
            verify=not self.settings.ignore_https_errors,
        )
        logger.info(
            "client_started", headless=self.settings.headless, stealth=self.settings.use_stealth
        )

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        self._started = False
        self._html_cache.clear()

    async def check_health(self) -> dict[str, Any]:
        now = time.monotonic()
        result: dict[str, Any] = {
            "status": "ok",
            "started": self._started,
            "circuit_breaker_state": self._circuit_breaker.state,
            "cache_size": len(self._html_cache),
        }
        if not self._started:
            result["status"] = "not_started"
            return result
        try:
            page = await self._context.new_page() if self._context else None
            if page:
                await page.close()
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
        self._last_health_check = now
        return result

    async def _ensure_browser(self) -> None:
        if not self._started:
            raise BrowserNotAvailable("Client not started")
        health = await self.check_health()
        if health["status"] == "error":
            logger.warning("browser_unhealthy_restarting", error=health.get("error"))
            await self.close()
            await self.start()

    async def _new_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("Client not started")
        return await self._context.new_page()

    async def _sleep(self) -> None:
        jitter = random.uniform(0, self.settings.delay_between_requests * 0.5)
        await asyncio.sleep(self.settings.delay_between_requests + jitter)

    async def _fetch_html_cached(self, url: str) -> str:
        async with self._html_cache_lock:
            existing = self._html_cache.get(url)
            if existing is not None:
                return await existing
            future = asyncio.get_running_loop().create_future()
            self._html_cache[url] = future
        try:
            html = await self._fetch_html(url)
            future.set_result(html)
        except BaseException:
            future.set_exception(sys.exc_info()[1])
            async with self._html_cache_lock:
                self._html_cache.pop(url, None)
            raise
        return html

    def clear_cache(self) -> None:
        self._html_cache.clear()

    async def _login(self) -> str:
        if self._http is None:
            raise RuntimeError("Client not started")
        username = self.settings.web_username
        password = self.settings.web_password
        if not username or not password:
            raise FatalError("AIGENIS_WEB_USERNAME/PASSWORD not set")
        resp = await self._http.post(
            f"{API_BASE}/v4/user/sign-in/",
            data={"identifier": username, "password": password},
        )
        if resp.status_code != 200:
            raise FatalError(
                f"API login failed: {resp.status_code} {resp.text[:200]}"
            )
        data = resp.json()
        token = data.get("access")
        if not token:
            raise FatalError("No access token in login response")
        self._token = token
        self._token_expires = time.monotonic() + 43200  # 12 hours
        logger.info("api_login_success")
        return token

    async def _ensure_authenticated(self, force: bool = False) -> None:
        async with self._auth_lock:
            if force or not self._token or time.monotonic() >= self._token_expires:
                await self._login()

    async def _api_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        if self._http is None:
            raise RuntimeError("Client not started")
        await self._ensure_authenticated()
        url = f"{API_BASE}{path}"
        headers = {"Authorization": f"JWT {self._token}"}
        try:
            if method.upper() == "GET":
                resp = await self._http.get(url, params=params, headers=headers)
            elif method.upper() == "POST":
                resp = await self._http.post(url, params=params, headers=headers)
            else:
                raise ValueError(f"unsupported method {method}")
        except httpx.TransportError as e:
            raise TransientError(f"transport error calling {url}: {e}") from e

        if resp.status_code == 404:
            raise NotFoundError(f"{url} returned 404")
        if resp.status_code == 401:
            logger.warning("api_token_expired_renewing")
            await self._login()
            headers = {"Authorization": f"JWT {self._token}"}
            if method.upper() == "POST":
                resp = await self._http.post(url, params=params, headers=headers)
            else:
                resp = await self._http.get(url, params=params, headers=headers)
        if resp.status_code >= 400:
            raise FatalError(f"API returned {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def _retrying(self, func, *args, **kwargs):
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((TransientError, PlaywrightTimeoutError)),
            before_sleep=before_sleep_log(logger, 30),
            reraise=True,
        ):
            with attempt:
                async with self._circuit_breaker:
                    return await func(*args, **kwargs)
        raise RuntimeError("unreachable")

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        if self._context is None:
            raise RuntimeError("Client not started")
        async with self._semaphore:
            page = await self._new_page()
            try:

                async def _do_request() -> Any:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.settings.timeout * 1000,
                    )
                    return response

                response = await self._retrying(_do_request)
                if response is None:
                    raise TransientError(f"empty response from {url}")
                status = response.status
                if status == 404:
                    raise NotFoundError(f"{url} returned 404")
                if status == 429:
                    raise TransientError(f"{url} returned 429 (rate limited)")
                if status >= 500:
                    raise TransientError(f"{url} returned {status}")
                if status >= 400:
                    raise FatalError(f"{url} returned {status}")
                try:
                    return await response.json()
                except Exception as e:
                    raise TransientError(f"json decode failed for {url}: {e}") from e
            finally:
                await page.close()
                await self._sleep()

    async def _fetch_html(self, url: str) -> str:
        if self._context is None:
            raise RuntimeError("Client not started")
        async with self._semaphore:
            page = await self._new_page()
            try:

                async def _do_request() -> Any:
                    response = await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=self.settings.timeout * 1000,
                    )
                    return response

                response = await self._retrying(_do_request)
                if response is None:
                    raise TransientError(f"empty response from {url}")
                status = response.status
                if status == 404:
                    raise NotFoundError(f"{url} returned 404")
                if status == 429:
                    raise TransientError(f"{url} returned 429 (rate limited)")
                if status >= 500:
                    raise TransientError(f"{url} returned {status}")
                if status >= 400:
                    raise FatalError(f"{url} returned {status}")
                with suppress(Exception):
                    await page.evaluate(
                        """async () => {
                            const sleep = ms => new Promise(r => setTimeout(r, ms));
                            for (let y = 0; y < document.body.scrollHeight; y += 600) {
                                window.scrollTo(0, y);
                                await sleep(200);
                            }
                            window.scrollTo(0, 0);
                            await sleep(500);
                        }"""
                    )
                return await page.content()
            finally:
                await page.close()
                await self._sleep()

    async def fetch_listing(self, currency: str) -> list[dict[str, Any]]:
        if self.settings.data_api_url:
            return await self._legacy_fetch_listing(currency)
        return await self._api_fetch_listing(currency)

    async def _legacy_fetch_listing(self, currency: str) -> list[dict[str, Any]]:
        await self._ensure_browser()
        url = f"{self.settings.data_api_url.rstrip('/')}/bonds?currency={currency}"
        try:
            data = await self._fetch_json(url)
            items = data.get("items") or data.get("data") or data
            if isinstance(items, dict):
                items = items.get("items", [])
            return [it for it in items if isinstance(it, dict)]
        except NotFoundError:
            raise
        except Exception as e:
            logger.warning("api_listing_failed", currency=currency, error=str(e))
        url = f"{self.settings.base_url.rstrip('/')}/bonds/"
        html = await self._fetch_html_cached(url)
        from scraper.parsers.listing import parse_listing_html

        return parse_listing_html(html, currency=currency)

    async def _api_fetch_listing(self, currency: str) -> list[dict[str, Any]]:
        self._id_by_internal.clear()
        page_num = 1
        all_normalized: list[dict[str, Any]] = []
        while True:
            data = await self._api_request(
                "GET",
                "/v1/security_definition/bonds/",
                params={"page": page_num, "page_size": 100},
            )
            items = data.get("results") if isinstance(data, dict) else data
            if not items or not isinstance(items, list):
                break
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Currency filter: settl_currency at top level, or definition.currency
                item_currency = (
                    item.get("settl_currency")
                    or item.get("definition", {}).get("currency")
                    or ""
                )
                if item_currency.upper() != currency.upper():
                    continue
                # internal_id from definition.state_security_id, or parse from symbol (id/state_security_id)
                defn = item.get("definition") or {}
                iid = defn.get("state_security_id")
                if not iid:
                    sym = item.get("symbol", "")
                    iid = sym.rsplit("/", 1)[-1] if "/" in sym else sym
                if not iid:
                    continue
                self._id_by_internal[str(iid)] = item.get("id")
                normalized = self._normalize_listing_item(item, currency)
                if normalized:
                    all_normalized.append(normalized)
            # API does not return count; stop when page has fewer items than page_size
            if len(items) < 100:
                break
            page_num += 1
        logger.info(
            "api_listing_fetched",
            currency=currency,
            count=len(all_normalized),
        )
        return all_normalized

    def _normalize_listing_item(
        self,
        item: dict[str, Any],
        currency: str,
    ) -> dict[str, Any] | None:
        from datetime import UTC, datetime

        defn = item.get("definition") or {}
        iid = defn.get("state_security_id") or item.get("symbol", "")
        if "/" in iid and defn.get("state_security_id"):
            iid = defn["state_security_id"]
        elif "/" in iid:
            iid = iid.rsplit("/", 1)[-1]
        if not iid:
            return None
        issuer_obj = defn.get("issuer") or {}
        issuer_logo = None
        for key in ("logo", "image", "image_url", "photo", "avatar"):
            val = issuer_obj.get(key)
            if val:
                issuer_logo = _abs_url(val)
                break
        return {
            "internal_id": str(iid),
            "name": str(defn.get("parent_symbol") or item.get("name_of_security") or iid),
            "currency": str(item.get("settl_currency") or defn.get("currency") or currency).upper(),
            "isin": item.get("isin"),
            "nominal": defn.get("nominal"),
            "coupon_rate": defn.get("coupon_rate"),
            "coupon_frequency": defn.get("coupon_frequency"),
            "registration_number": defn.get("state_security_id"),
            "issue_number": defn.get("issue_number"),
            "issue_volume": defn.get("quantity") or item.get("quantity"),
            "income_method": defn.get("income_method"),
            "in_stock": defn.get("available_for_individuals"),
            "guarantor": None,
            "maturity_term_text": str(
                defn.get("time_to_maturity_years") or ""
            ) if defn.get("time_to_maturity_years") else None,
            "coupon_description": defn.get("coupon_description"),
            "coupon_schedule": defn.get("coupon_schedule"),
            "issuer": (defn.get("issuer") or {}).get("full_name"),
            "issuer_logo": issuer_logo,
            "end_date": defn.get("maturity_date"),
            "maturity_date": defn.get("maturity_date"),
            "price": defn.get("price"),
            "yield_to_maturity": defn.get("instr_yield"),
            "market_price": defn.get("market_price") or item.get("market_price"),
            "best_bid": item.get("best_bid") or defn.get("best_bid"),
            "best_offer": item.get("best_offer") or defn.get("best_offer"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    async def fetch_detail(self, internal_id: str) -> dict[str, Any]:
        if self.settings.data_api_url:
            return await self._legacy_fetch_detail(internal_id)
        return await self._api_fetch_detail(internal_id)

    async def _legacy_fetch_detail(self, internal_id: str) -> dict[str, Any]:
        await self._ensure_browser()
        url = f"{self.settings.data_api_url.rstrip('/')}/bonds/{internal_id}"
        try:
            return await self._fetch_json(url)
        except NotFoundError:
            raise
        except Exception as e:
            logger.warning("api_detail_failed", internal_id=internal_id, error=str(e))
        url = f"{self.settings.base_url.rstrip('/')}/bonds/"
        html = await self._fetch_html_cached(url)
        from scraper.parsers.detail import parse_detail_html

        return parse_detail_html(html, internal_id=internal_id)

    async def _api_fetch_detail(self, internal_id: str) -> dict[str, Any]:
        from datetime import UTC, datetime

        bond_id = self._id_by_internal.get(internal_id)
        if not bond_id:
            msg = f"internal_id {internal_id} not found in listing; ensure fetch_listing ran first"
            raise NotFoundError(msg)
        data = await self._api_request("GET", f"/v1/security_definition/{bond_id}/")
        if not isinstance(data, dict):
            raise ParseError(f"unexpected API response for {internal_id}")
        defn = data.get("definition") or {}
        iid = defn.get("state_security_id") or internal_id
        sym = data.get("symbol", "")
        if not defn.get("state_security_id") and "/" in sym:
            iid = sym.rsplit("/", 1)[-1]
        issuer_obj = defn.get("issuer") or {}
        issuer_logo = None
        for key in ("logo", "image", "image_url", "photo", "avatar"):
            val = issuer_obj.get(key)
            if val:
                issuer_logo = _abs_url(val)
                break
        return {
            "id": iid,
            "internal_id": iid,
            "name": str(defn.get("parent_symbol") or data.get("name_of_security") or iid),
            "issuer": (defn.get("issuer") or {}).get("full_name"),
            "issuer_logo": issuer_logo,
            "currency": str(defn.get("currency") or data.get("settl_currency", "USD")).upper(),
            "nominal": defn.get("nominal"),
            "coupon_rate": defn.get("coupon_rate"),
            "coupon_frequency": defn.get("coupon_frequency"),
            "maturity_date": defn.get("maturity_date"),
            "price": defn.get("price"),
            "yield_to_maturity": defn.get("instr_yield"),
            "offer_date": None,
            "start_date": defn.get("issue_date"),
            "end_date": defn.get("maturity_date"),
            "isin": defn.get("security_symbol"),
            "status": "active",
            "registration_number": defn.get("state_security_id"),
            "issue_volume": defn.get("quantity"),
            "issue_number": defn.get("issue_number"),
            "income_method": defn.get("revenue_type"),
            "in_stock": defn.get("available_for_individuals"),
            "guarantor": None,
            "maturity_term_text": str(
                defn.get("time_to_maturity_years") or ""
            ) if defn.get("time_to_maturity_years") else None,
            "coupon_description": defn.get("coupon_description"),
            "coupon_schedule": defn.get("coupon_schedule"),
            "quantity": defn.get("quantity"),
            "issuer_country": defn.get("issuer_country"),
            "market_price": defn.get("market_price") or data.get("market_price"),
            "best_bid": data.get("best_bid") or defn.get("best_bid"),
            "best_offer": data.get("best_offer") or defn.get("best_offer"),
            "accrued_interest_amount": defn.get("accrued_interest_amount"),
            "calc_yield_bid": data.get("calc_yield_bid") or defn.get("calc_yield_bid"),
            "calc_yield_offer": data.get("calc_yield_offer") or defn.get("calc_yield_offer"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    async def fetch_history(
        self,
        internal_id: str,
        since: date,
        until: date | None = None,
    ) -> list[dict[str, Any]]:
        await self._ensure_browser()
        until_q = f"&until={until.isoformat()}" if until else ""
        if self.settings.data_api_url:
            url = (
                f"{self.settings.data_api_url.rstrip('/')}"
                f"/bonds/{internal_id}/history?since={since.isoformat()}{until_q}"
            )
            try:
                data = await self._fetch_json(url)
                items = data.get("items") or data.get("data") or data
                if isinstance(items, dict):
                    items = items.get("items", [])
                return [it for it in items if isinstance(it, dict)]
            except NotFoundError:
                raise
            except Exception as e:
                logger.warning("api_history_failed", internal_id=internal_id, error=str(e))
            from scraper.errors import HistoryUnavailable

            raise HistoryUnavailable(f"history not available for {internal_id}")

        # API mode (invest.aigenis.by). Fetch historical quotes and normalise
        # them into the shape ``parse_history_payload`` expects.
        return await self._api_fetch_history(internal_id, since, until)

    async def _api_fetch_history(
        self,
        internal_id: str,
        since: date,
        until: date | None,
    ) -> list[dict[str, Any]]:
        from scraper.errors import HistoryUnavailable

        template = (self.settings.api_history_path or "").strip()
        if not template:
            raise HistoryUnavailable("history disabled (AIGENIS_API_HISTORY_PATH empty)")

        bond_id = self._id_by_internal.get(internal_id)
        if not bond_id:
            raise NotFoundError(
                f"internal_id {internal_id} not found in listing; ensure fetch_listing ran first"
            )

        path = template.format(id=bond_id)
        params: dict[str, Any] = {
            "date_from": since.isoformat(),
            "date_to": (until or date.today()).isoformat(),
            "page_size": 500,
        }
        try:
            rows: list[dict[str, Any]] = []
            page_num = 1
            while True:
                params["page"] = page_num
                data = await self._api_request("GET", path, params=params)
                items = data.get("results") if isinstance(data, dict) else data
                if not items or not isinstance(items, list):
                    break
                for it in items:
                    if isinstance(it, dict):
                        normalized = self._normalize_history_item(it)
                        if normalized:
                            rows.append(normalized)
                if len(items) < 500:
                    break
                page_num += 1
            logger.info("api_history_fetched", internal_id=internal_id, count=len(rows))
            return rows
        except NotFoundError:
            # No history for this instrument — treat as "unavailable" so the
            # pipeline skips it instead of aborting the whole backfill.
            raise HistoryUnavailable(f"history endpoint 404 for {internal_id}") from None
        except HistoryUnavailable:
            raise
        except Exception as e:
            logger.warning("api_history_failed", internal_id=internal_id, error=str(e))
            raise HistoryUnavailable(f"history fetch failed for {internal_id}") from e

    @staticmethod
    def _normalize_history_item(it: dict[str, Any]) -> dict[str, Any] | None:
        """Map an API quote/candle row to the parser's ``{date, price, yield,
        coupon, status}`` schema, tolerating several common field names."""
        d = (
            it.get("date")
            or it.get("timestamp")
            or it.get("trade_date")
            or it.get("dt")
            or it.get("day")
        )
        if not d:
            return None
        price = (
            it.get("price")
            if it.get("price") is not None
            else it.get("close")
            if it.get("close") is not None
            else it.get("last")
            if it.get("last") is not None
            else it.get("market_price")
        )
        yield_val = (
            it.get("yield")
            if it.get("yield") is not None
            else it.get("instr_yield")
            if it.get("instr_yield") is not None
            else it.get("yield_to_maturity")
        )
        return {
            "date": d,
            "price": price,
            "yield": yield_val,
            "coupon": it.get("coupon") if it.get("coupon") is not None else it.get("coupon_rate"),
            "status": it.get("status", "unknown"),
        }


@asynccontextmanager
async def aigenis_client():
    client = AigenisClient()
    try:
        await client.start()
        yield client
    finally:
        await client.close()
