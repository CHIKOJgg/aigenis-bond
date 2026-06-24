"""Aigenis HTTP/Playwright client.

Приоритет — внутренний JSON endpoint (если задан DATA_API_URL).
Fallback — рендеринг страницы через Chromium и парсинг DOM.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from contextlib import asynccontextmanager, suppress
from datetime import date
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)
from playwright_stealth import Stealth
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.config import Settings, get_settings
from scraper.errors import FatalError, NotFoundError, TransientError
from scraper.logging import get_logger

logger = get_logger("scraper.client")


class AigenisClient:
    """Клиент к Aigenis: JSON API приоритетно, DOM fallback."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrency)
        self._stealth = Stealth() if self.settings.use_stealth else None
        # Кэш HTML по URL — Future-based single-fly для параллельных запросов
        self._html_cache: dict[str, asyncio.Future[str]] = {}
        self._html_cache_lock = asyncio.Lock()

    async def __aenter__(self) -> AigenisClient:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=self.settings.user_agent,
            locale="ru-RU",
            timezone_id="Europe/Minsk",
            ignore_https_errors=True,
        )
        if self._stealth is not None:
            try:
                await self._stealth.apply_context(self._context)
            except Exception as e:  # noqa: BLE001
                logger.warning("stealth_apply_failed", error=str(e))
        logger.info("client_started", headless=self.settings.headless, stealth=self.settings.use_stealth)

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

    async def _new_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("Client not started")
        return await self._context.new_page()

    async def _sleep(self) -> None:
        jitter = random.uniform(0, self.settings.delay_between_requests * 0.5)
        await asyncio.sleep(self.settings.delay_between_requests + jitter)

    async def _fetch_html_cached(self, url: str) -> str:
        """Fetch HTML с in-memory кэшем. Future-based single-fly."""
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
        """Очистить in-memory кэш HTML (для тестов и долгих сессий)."""
        self._html_cache.clear()

    async def _retrying(self, func, *args, **kwargs):
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.settings.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((TransientError, PlaywrightTimeoutError)),
            reraise=True,
        ):
            with attempt:
                return await func(*args, **kwargs)
        raise RuntimeError("unreachable")

    async def _fetch_json(self, url: str) -> dict[str, Any]:
        """GET JSON через контекст браузера (с cookie/site context)."""
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
                if status >= 500:
                    raise TransientError(f"{url} returned {status}")
                if status >= 400:
                    raise FatalError(f"{url} returned {status}")
                try:
                    return await response.json()
                except Exception as e:  # noqa: BLE001
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
                if status >= 500:
                    raise TransientError(f"{url} returned {status}")
                if status >= 400:
                    raise FatalError(f"{url} returned {status}")
                # Дополнительное ожидание: скроллим, чтобы догрузить контент
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
        """Список облигаций по валюте."""
        if self.settings.data_api_url:
            url = f"{self.settings.data_api_url.rstrip('/')}/bonds?currency={currency}"
            try:
                data = await self._fetch_json(url)
                items = data.get("items") or data.get("data") or data
                if isinstance(items, dict):
                    items = items.get("items", [])
                return [it for it in items if isinstance(it, dict)]
            except NotFoundError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning("api_listing_failed", currency=currency, error=str(e))
        # aigenis.by использует единый каталог /bonds/, фильтрация по валюте — клиентская
        url = f"{self.settings.base_url.rstrip('/')}/bonds/"
        html = await self._fetch_html_cached(url)
        from scraper.parsers.listing import parse_listing_html

        return parse_listing_html(html, currency=currency)

    async def fetch_detail(self, internal_id: str) -> dict[str, Any]:
        if self.settings.data_api_url:
            url = f"{self.settings.data_api_url.rstrip('/')}/bonds/{internal_id}"
            try:
                return await self._fetch_json(url)
            except NotFoundError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning("api_detail_failed", internal_id=internal_id, error=str(e))
        url = f"{self.settings.base_url.rstrip('/')}/bonds/"
        html = await self._fetch_html_cached(url)
        from scraper.parsers.detail import parse_detail_html

        return parse_detail_html(html, internal_id=internal_id)

    async def fetch_history(
        self,
        internal_id: str,
        since: date,
        until: date | None = None,
    ) -> list[dict[str, Any]]:
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
            except Exception as e:  # noqa: BLE001
                logger.warning("api_history_failed", internal_id=internal_id, error=str(e))
        # aigenis.by не предоставляет отдельных страниц истории — данные идут на одной странице
        from scraper.errors import HistoryUnavailable

        raise HistoryUnavailable(f"history not available for {internal_id}")


@asynccontextmanager
async def aigenis_client():
    """Удобный контекстный менеджер."""
    client = AigenisClient()
    try:
        await client.start()
        yield client
    finally:
        await client.close()


def main() -> None:
    """Smoke-тест клиента (не запускать в проде)."""
    import json
    from datetime import timedelta

    if not os.getenv("AIGENIS_SMOKE"):
        print("Set AIGENIS_SMOKE=1 to run smoke test")
        return

    async def _run() -> None:
        async with aigenis_client() as client:
            items = await client.fetch_listing("USD")
            print(f"listing USD: {len(items)} items")
            if items:
                first = items[0]
                internal_id = str(first.get("id") or first.get("internal_id"))
                detail = await client.fetch_detail(internal_id)
                print(json.dumps(detail, ensure_ascii=False, indent=2)[:500])
                today = date.today()
                hist = await client.fetch_history(internal_id, today - timedelta(days=30))
                print(f"history rows: {len(hist)}")

    asyncio.run(_run())


if __name__ == "__main__":
    main()
