from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from scraper.errors import (
    BrowserNotAvailable,
    CircuitBreakerOpenError,
    FatalError,
    HistoryUnavailable,
    NotFoundError,
    ParseError,
    TransientError,
)
from scraper.sources.aigenis import client as client_mod
from scraper.sources.aigenis.client import (
    _FX_CACHE,
    AigenisClient,
    _abs_url,
    _byn_per_ccy,
    _CircuitBreaker,
    _sane_coupon_rate,
    _sane_yield,
    _to_price_pct,
    aigenis_client,
)


class FakeResponse:
    def __init__(self, status: int = 200, payload=None, json_error: bool = False):
        self.status = status
        self._payload = payload
        self.json_error = json_error

    async def json(self):
        if self.json_error:
            raise ValueError("bad json")
        return self._payload

    @property
    def text(self) -> str:
        return "resp-text"


class FakePage:
    def __init__(self, response=None, html="<html></html>"):
        self.response = response
        self._html = html
        self.closed = False
        self.evaluate_calls: list[str] = []
        self.goto_kwargs = None

    async def goto(self, url, **kwargs):
        self.goto_kwargs = kwargs
        return self.response

    async def evaluate(self, script):
        self.evaluate_calls.append(script)

    async def content(self):
        return self._html

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, responses=None, page_class=None):
        self.pages: list[FakePage] = []
        self.closed = False
        self.new_page_error: Exception | None = None
        self._responses = list(responses) if responses else []
        self._page_class = page_class or FakePage

    async def new_page(self):
        if self.new_page_error is not None:
            raise self.new_page_error
        page_cls = self._page_class
        page = page_cls(response=self._responses.pop(0) if self._responses else None)
        self.pages.append(page)
        return page

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self, context=None):
        self.context = context or FakeContext()
        self.closed = False
        self.launch_kwargs = None

    async def new_context(self, **kwargs):
        self.launch_kwargs = kwargs
        return self.context

    async def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser):
        self._browser = browser
        self.launch_kwargs = None

    async def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return self._browser


class FakePlaywright:
    def __init__(self, browser=None):
        self.browser = browser or FakeBrowser()
        self.stopped = False
        self.chromium = _FakeChromium(self.browser)

    async def stop(self):
        self.stopped = True


class _FakeAsyncPlaywright:
    def __init__(self, playwright):
        self._pw = playwright

    async def start(self):
        return self._pw


class FakeTimeoutError(Exception):
    pass


class FakeStealth:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.applied = False

    async def apply_context(self, context):
        self.applied = True
        if self.fail:
            raise RuntimeError("stealth boom")


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._next()

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next()

    async def aclose(self):
        pass

    def _next(self):
        return self.responses.pop(0) if self.responses else httpx.Response(500)


def make_settings(**overrides):
    base = {
        "base_url": "https://aigenis.by",
        "web_username": "user",
        "web_password": "pass",
        "data_api_url": None,
        "api_history_path": "/v1/security_history/{id}/",
        "headless": True,
        "use_stealth": True,
        "delay_between_requests": 0.0,
        "max_concurrency": 2,
        "max_retries": 1,
        "timeout": 30,
        "ignore_https_errors": False,
        "user_agent": "test-ua",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def make_client():
    def _make(**overrides):
        return AigenisClient(make_settings(**overrides))

    return _make


@pytest.fixture
def fx_cache():
    saved = dict(_FX_CACHE)
    _FX_CACHE.clear()
    yield
    _FX_CACHE.clear()
    _FX_CACHE.update(saved)


@pytest.fixture
def pw_fake(monkeypatch):
    def _patch(fail_stealth=False, browser=None):
        playwright = FakePlaywright(browser=browser)

        class _Stealth:
            def __init__(self, fail=fail_stealth):
                self.fail = fail
                self.applied = False

            async def apply_context(self, context):
                self.applied = True
                if self.fail:
                    raise RuntimeError("stealth boom")

        monkeypatch.setattr(
            client_mod,
            "_playwright_imports",
            lambda: (lambda: _FakeAsyncPlaywright(playwright), FakeTimeoutError, _Stealth),
        )
        return playwright

    return _patch


class TestAbsUrl:
    def test_none(self):
        assert _abs_url(None) is None

    def test_absolute_http(self):
        assert _abs_url("http://x.com/logo.png") == "http://x.com/logo.png"

    def test_absolute_https(self):
        assert _abs_url("https://x.com/logo.png") == "https://x.com/logo.png"

    def test_leading_slash(self):
        assert _abs_url("/logo.png") == client_mod.SITE_BASE + "/logo.png"

    def test_bare_path(self):
        assert _abs_url("logo.png") == client_mod.SITE_BASE + "/logo.png"


class TestBynPerCcy:
    @pytest.mark.asyncio
    async def test_cache_hit(self, fx_cache):
        _FX_CACHE["BYN"] = 1.0
        assert await _byn_per_ccy("BYN") == 1.0

    @pytest.mark.asyncio
    async def test_from_latest_fx(self, fx_cache, monkeypatch):
        row = SimpleNamespace(rate=2.5)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope(session=None):
            yield SimpleNamespace()

        monkeypatch.setattr("scraper.db.session_scope", fake_scope)
        monkeypatch.setattr("notifications.fx_repository.latest_fx", AsyncMock(return_value=row))
        assert await _byn_per_ccy("USD") == 2.5
        assert _FX_CACHE["USD"] == 2.5

    @pytest.mark.asyncio
    async def test_from_live_rates(self, fx_cache, monkeypatch):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope(session=None):
            yield SimpleNamespace()

        monkeypatch.setattr("scraper.db.session_scope", fake_scope)
        monkeypatch.setattr("notifications.fx_repository.latest_fx", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "scraper.fx.fetch_and_save_rates", AsyncMock(return_value={"EUR/BYN": 3.1})
        )
        assert await _byn_per_ccy("EUR") == 3.1

    @pytest.mark.asyncio
    async def test_rate_missing(self, fx_cache, monkeypatch):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope(session=None):
            yield SimpleNamespace()

        monkeypatch.setattr("scraper.db.session_scope", fake_scope)
        monkeypatch.setattr("notifications.fx_repository.latest_fx", AsyncMock(return_value=None))
        monkeypatch.setattr(
            "scraper.fx.fetch_and_save_rates", AsyncMock(return_value={"USD/BYN": 2.9})
        )
        assert await _byn_per_ccy("RUB") is None

    @pytest.mark.asyncio
    async def test_all_failures(self, fx_cache, monkeypatch):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_scope(session=None):
            yield SimpleNamespace()

        monkeypatch.setattr("scraper.db.session_scope", fake_scope)
        monkeypatch.setattr(
            "notifications.fx_repository.latest_fx", AsyncMock(side_effect=RuntimeError("boom"))
        )
        monkeypatch.setattr(
            "scraper.fx.fetch_and_save_rates", AsyncMock(side_effect=RuntimeError("boom"))
        )
        monkeypatch.setattr(client_mod.logger, "warning", lambda *a, **k: None)
        assert await _byn_per_ccy("CNY") is None


class TestToPricePct:
    @pytest.mark.asyncio
    async def test_none(self):
        assert await _to_price_pct(None, 1000, "USD") is None

    @pytest.mark.asyncio
    async def test_empty(self):
        assert await _to_price_pct("", 1000, "USD") is None

    @pytest.mark.asyncio
    async def test_bad_value(self):
        assert await _to_price_pct("abc", 1000, "USD") == "abc"

    @pytest.mark.asyncio
    async def test_zero_or_negative_price(self):
        assert await _to_price_pct("0", 1000, "USD") is None
        assert await _to_price_pct("-5", 1000, "USD") is None

    @pytest.mark.asyncio
    async def test_nominal_none(self):
        assert await _to_price_pct("100", None, "USD") == "100"

    @pytest.mark.asyncio
    async def test_bad_nominal(self):
        assert await _to_price_pct("100", "abc", "USD") == "100"

    @pytest.mark.asyncio
    async def test_zero_nominal(self):
        assert await _to_price_pct("100", 0, "USD") == "100"

    @pytest.mark.asyncio
    async def test_fx_unavailable(self, monkeypatch):
        # Without an FX anchor for a non-BYN issue we cannot normalize the raw
        # settlement amount to percent-of-face, so we report "insufficient data"
        # (None) rather than persisting a corrupt percentile.
        monkeypatch.setattr(client_mod, "_byn_per_ccy", AsyncMock(return_value=None))
        assert await _to_price_pct("100", 1000, "USD") is None

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        monkeypatch.setattr(client_mod, "_byn_per_ccy", AsyncMock(return_value=2.9))
        result = await _to_price_pct("2938.6", 1000, "USD")
        assert isinstance(result, float)
        assert abs(result - 101.331034) < 0.001

    @pytest.mark.asyncio
    async def test_byn_identity_without_fx(self, monkeypatch):
        # BYN issues are quoted in BYN: even when the FX lookup fails, the
        # rate is treated as identity instead of dropping the price.
        monkeypatch.setattr(client_mod, "_byn_per_ccy", AsyncMock(return_value=None))
        result = await _to_price_pct("101.5", 1000, "BYN")
        assert isinstance(result, float)
        assert abs(result - 10.15) < 0.001

    @pytest.mark.asyncio
    async def test_out_of_range_keeps_raw(self, monkeypatch):
        # A quote far outside 0.5-500% of face is a unit mismatch: keep the raw
        # value so read-time normalization can retry with better context.
        monkeypatch.setattr(client_mod, "_byn_per_ccy", AsyncMock(return_value=1.0))
        monkeypatch.setattr(client_mod.logger, "warning", lambda *a, **k: None)
        assert await _to_price_pct("123456", 1000, "USD") == "123456"


class TestSaneCouponRate:
    def test_none(self):
        assert _sane_coupon_rate(None) is None

    def test_empty(self):
        assert _sane_coupon_rate("") is None

    def test_bad_value(self):
        assert _sane_coupon_rate("abc") == "abc"

    def test_positive(self):
        assert _sane_coupon_rate("7.5") == "7.5"

    def test_zero_is_missing(self):
        # 0.0 means "coupon not disclosed" (indexed bonds), not a zero coupon.
        assert _sane_coupon_rate("0") is None
        assert _sane_coupon_rate(0.0) is None
        assert _sane_coupon_rate(Decimal("0.00")) is None

    def test_negative_is_missing(self):
        assert _sane_coupon_rate("-1") is None


class TestSaneYield:
    def test_none(self):
        assert _sane_yield(None) is None

    def test_empty(self):
        assert _sane_yield("") is None

    def test_bad_value(self):
        assert _sane_yield("abc") == "abc"

    def test_positive(self):
        assert _sane_yield("3.5") == "3.5"

    def test_zero(self):
        assert _sane_yield("0") is None

    def test_negative(self):
        assert _sane_yield("-1.2") is None


class TestNormalizeHistoryItem:
    @pytest.mark.asyncio
    async def test_full(self):
        assert await AigenisClient._normalize_history_item(
            {"date": "2024-01-01", "price": 101.5, "yield": 3.2, "coupon": 7.5, "status": "active"}
        ) == {
            "date": "2024-01-01",
            "price": 101.5,
            "yield": Decimal("3.2"),
            "coupon": 7.5,
            "status": "active",
        }

    @pytest.mark.asyncio
    async def test_timestamp(self):
        assert (await AigenisClient._normalize_history_item({"timestamp": "t", "price": 1}))["date"] == "t"

    @pytest.mark.asyncio
    async def test_trade_date(self):
        assert (
            (await AigenisClient._normalize_history_item({"trade_date": "td", "price": 1}))["date"]
            == "td"
        )

    @pytest.mark.asyncio
    async def test_dt(self):
        assert (await AigenisClient._normalize_history_item({"dt": "dt", "price": 1}))["date"] == "dt"

    @pytest.mark.asyncio
    async def test_day(self):
        assert (await AigenisClient._normalize_history_item({"day": "d", "price": 1}))["date"] == "d"

    @pytest.mark.asyncio
    async def test_no_date(self):
        assert await AigenisClient._normalize_history_item({"price": 1}) is None

    @pytest.mark.asyncio
    async def test_price_close_fallback(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "close": 5})
        assert item["price"] == 5

    @pytest.mark.asyncio
    async def test_price_last_fallback(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "last": 6})
        assert item["price"] == 6

    @pytest.mark.asyncio
    async def test_price_market_fallback(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "market_price": 7})
        assert item["price"] == 7

    @pytest.mark.asyncio
    async def test_price_all_missing(self):
        item = await AigenisClient._normalize_history_item({"date": "d"})
        assert item["price"] is None

    @pytest.mark.asyncio
    async def test_yield_instr_fallback(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "price": 1, "instr_yield": 4})
        assert item["yield"] == Decimal("4")

    @pytest.mark.asyncio
    async def test_yield_ytm_fallback(self):
        item = await AigenisClient._normalize_history_item(
            {"date": "d", "price": 1, "yield_to_maturity": 4}
        )
        assert item["yield"] == Decimal("4")

    @pytest.mark.asyncio
    async def test_yield_negative_none(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "price": 1, "yield": -3})
        assert item["yield"] is None

    @pytest.mark.asyncio
    async def test_yield_extreme_none(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "price": 1, "yield": 1545})
        assert item["yield"] is None

    @pytest.mark.asyncio
    async def test_coupon_rate_fallback(self):
        item = await AigenisClient._normalize_history_item({"date": "d", "price": 1, "coupon_rate": 8})
        assert item["coupon"] == 8


class TestCircuitBreaker:
    def test_initial_closed(self):
        assert _CircuitBreaker().state == "closed"

    def test_opens_after_threshold(self, monkeypatch):
        monkeypatch.setattr(client_mod.logger, "error", lambda *a, **k: None)
        cb = _CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        assert cb.state == "closed"
        cb.record_failure()
        assert cb.state == "open"

    def test_half_open_after_timeout(self):
        cb = _CircuitBreaker()
        cb._state = "open"
        cb._last_failure_time = time.monotonic() - 1000
        assert cb.state == "half-open"

    def test_record_success_resets(self):
        cb = _CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.state == "open"
        cb.record_success()
        assert cb.state == "closed"
        assert cb._failures == 0

    @pytest.mark.asyncio
    async def test_aenter_open_raises(self):
        cb = _CircuitBreaker()
        cb._state = "open"
        cb._last_failure_time = time.monotonic()
        with pytest.raises(CircuitBreakerOpenError):
            async with cb:
                pass

    @pytest.mark.asyncio
    async def test_aenter_closed_ok(self):
        cb = _CircuitBreaker()
        async with cb:
            assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_aexit_transient_failure(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "_playwright_imports", lambda: (None, FakeTimeoutError, None)
        )
        cb = _CircuitBreaker(failure_threshold=5)
        with pytest.raises(TransientError):
            async with cb:
                raise TransientError("x")
        assert cb._failures == 1

    @pytest.mark.asyncio
    async def test_aexit_pw_timeout_failure(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "_playwright_imports", lambda: (None, FakeTimeoutError, None)
        )
        cb = _CircuitBreaker(failure_threshold=5)
        with pytest.raises(FakeTimeoutError):
            async with cb:
                raise FakeTimeoutError("x")
        assert cb._failures == 1

    @pytest.mark.asyncio
    async def test_aexit_success_resets(self, monkeypatch):
        monkeypatch.setattr(
            client_mod, "_playwright_imports", lambda: (None, FakeTimeoutError, None)
        )
        cb = _CircuitBreaker()
        cb._failures = 3
        async with cb:
            pass
        assert cb._failures == 0
        assert cb.state == "closed"


class TestClientLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_up(self, make_client, pw_fake):
        playwright = pw_fake()
        client = make_client(use_stealth=True)
        await client.start()
        assert client._started is True
        assert client._stealth is not None
        assert client._stealth.applied is True
        assert playwright.chromium.launch_kwargs["headless"] is True
        assert playwright.browser.launch_kwargs["user_agent"] == "test-ua"
        assert playwright.browser.launch_kwargs["locale"] == "ru-RU"
        assert client._http is not None
        await client.close()

    @pytest.mark.asyncio
    async def test_start_stealth_failure_warns(self, make_client, pw_fake, monkeypatch):
        pw_fake(fail_stealth=True)
        monkeypatch.setattr(client_mod.logger, "warning", lambda *a, **k: None)
        client = make_client()
        await client.start()
        assert client._started is True
        await client.close()

    @pytest.mark.asyncio
    async def test_start_no_stealth(self, make_client, pw_fake):
        pw_fake()
        client = make_client(use_stealth=False)
        await client.start()
        assert client._stealth is None
        await client.close()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, make_client, monkeypatch):
        client = make_client()
        client._started = True
        monkeypatch.setattr(
            client_mod, "_playwright_imports", lambda: (_ for _ in ()).throw(AssertionError("no"))
        )
        await client.start()

    @pytest.mark.asyncio
    async def test_close_closes_everything(self, make_client, pw_fake):
        playwright = pw_fake()
        client = make_client()
        await client.start()
        await client.close()
        assert playwright.browser.context.closed is True
        assert playwright.browser.closed is True
        assert playwright.stopped is True
        assert client._http is None
        assert client._started is False

    @pytest.mark.asyncio
    async def test_close_partial(self, make_client):
        client = make_client()
        http = FakeHttp([])
        client._http = http
        await client.close()
        assert client._http is None

    @pytest.mark.asyncio
    async def test_aenter_aexit(self, make_client, pw_fake):
        pw_fake()
        client = make_client()
        async with client:
            assert client._started is True
        assert client._started is False

    @pytest.mark.asyncio
    async def test_check_health_not_started(self, make_client):
        client = make_client()
        result = await client.check_health()
        assert result["status"] == "not_started"
        assert result["started"] is False

    @pytest.mark.asyncio
    async def test_check_health_started_ok(self, make_client):
        client = make_client()
        client._started = True
        client._context = FakeContext()
        result = await client.check_health()
        assert result["status"] == "ok"
        assert result["cache_size"] == 0
        assert len(client._context.pages) == 1
        assert client._context.pages[0].closed is True

    @pytest.mark.asyncio
    async def test_check_health_new_page_error(self, make_client):
        client = make_client()
        client._started = True
        context = FakeContext()
        context.new_page_error = RuntimeError("boom")
        client._context = context
        result = await client.check_health()
        assert result["status"] == "error"
        assert "boom" in result["error"]

    @pytest.mark.asyncio
    async def test_ensure_browser_not_started(self, make_client):
        client = make_client()
        with pytest.raises(BrowserNotAvailable):
            await client._ensure_browser()

    @pytest.mark.asyncio
    async def test_ensure_browser_restarts_on_unhealthy(self, make_client, monkeypatch):
        client = make_client()
        client._started = True
        monkeypatch.setattr(
            client, "check_health", AsyncMock(return_value={"status": "error", "error": "x"})
        )
        close_mock = AsyncMock()
        start_mock = AsyncMock()
        monkeypatch.setattr(client, "close", close_mock)
        monkeypatch.setattr(client, "start", start_mock)
        await client._ensure_browser()
        close_mock.assert_awaited_once()
        start_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ensure_browser_healthy(self, make_client, monkeypatch):
        client = make_client()
        client._started = True
        monkeypatch.setattr(client, "check_health", AsyncMock(return_value={"status": "ok"}))
        close_mock = AsyncMock()
        monkeypatch.setattr(client, "close", close_mock)
        await client._ensure_browser()
        close_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_new_page_context_none(self, make_client):
        client = make_client()
        with pytest.raises(RuntimeError):
            await client._new_page()

    @pytest.mark.asyncio
    async def test_new_page_ok(self, make_client):
        client = make_client()
        client._context = FakeContext()
        page = await client._new_page()
        assert page is client._context.pages[0]

    @pytest.mark.asyncio
    async def test_sleep(self, make_client, monkeypatch):
        client = make_client(delay_between_requests=2.0)
        monkeypatch.setattr(client_mod.random, "uniform", lambda *a, **k: 1.0)
        sleeps: list[float] = []
        real_sleep = asyncio.sleep

        async def fake_sleep(delay):
            sleeps.append(delay)

        monkeypatch.setattr(client_mod.asyncio, "sleep", fake_sleep)
        await client._sleep()
        assert sleeps == [3.0]
        await real_sleep(0)

    @pytest.mark.asyncio
    async def test_fetch_html_cached_success(self, make_client, monkeypatch):
        client = make_client()
        monkeypatch.setattr(client, "_fetch_html", AsyncMock(return_value="<html>"))
        assert await client._fetch_html_cached("u") == "<html>"

    @pytest.mark.asyncio
    async def test_fetch_html_cached_reuse(self, make_client, monkeypatch):
        client = make_client()
        fetch = AsyncMock(return_value="<html>")
        monkeypatch.setattr(client, "_fetch_html", fetch)
        await client._fetch_html_cached("u")
        await client._fetch_html_cached("u")
        fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_html_cached_error_pops(self, make_client, monkeypatch):
        client = make_client()
        fetch = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(client, "_fetch_html", fetch)
        with pytest.raises(RuntimeError):
            await client._fetch_html_cached("u")
        assert "u" not in client._html_cache

    def test_clear_cache(self, make_client):
        client = make_client()
        client._html_cache["u"] = object()
        client.clear_cache()
        assert client._html_cache == {}


class TestLogin:
    @pytest.mark.asyncio
    async def test_http_none_raises(self, make_client):
        client = make_client()
        with pytest.raises(RuntimeError):
            await client._login()

    @pytest.mark.asyncio
    async def test_no_credentials_warns(self, make_client, monkeypatch):
        client = make_client(web_username="", web_password="")
        client._http = FakeHttp([])
        monkeypatch.setattr(client_mod.logger, "warning", lambda *a, **k: None)
        assert await client._login() == ""
        assert client._token is None

    @pytest.mark.asyncio
    async def test_success(self, make_client):
        client = make_client()
        client._http = FakeHttp([httpx.Response(200, json={"access": "tok"})])
        token = await client._login()
        assert token == "tok"
        assert client._token == "tok"
        assert client._token_expires > time.monotonic()
        assert client._http.calls[0][0] == "POST"
        assert "v4/user/sign-in/" in client._http.calls[0][1]

    @pytest.mark.asyncio
    async def test_http_error_fatal(self, make_client):
        client = make_client()
        client._http = FakeHttp([httpx.Response(401, text="denied")])
        with pytest.raises(FatalError):
            await client._login()

    @pytest.mark.asyncio
    async def test_no_access_token_fatal(self, make_client):
        client = make_client()
        client._http = FakeHttp([httpx.Response(200, json={"refresh": "x"})])
        with pytest.raises(FatalError):
            await client._login()


class TestEnsureAuthenticated:
    @pytest.mark.asyncio
    async def test_no_credentials(self, make_client):
        client = make_client(web_username="", web_password="")
        client._token = "stale"
        await client._ensure_authenticated()
        assert client._token is None

    @pytest.mark.asyncio
    async def test_force_logs_in(self, make_client, monkeypatch):
        client = make_client()
        login = AsyncMock(return_value="tok")
        monkeypatch.setattr(client, "_login", login)
        await client._ensure_authenticated(force=True)
        login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_token_fresh_skips(self, make_client, monkeypatch):
        client = make_client()
        client._token = "tok"
        client._token_expires = time.monotonic() + 3600
        login = AsyncMock()
        monkeypatch.setattr(client, "_login", login)
        await client._ensure_authenticated()
        login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_token_expired_logs_in(self, make_client, monkeypatch):
        client = make_client()
        client._token = "tok"
        client._token_expires = time.monotonic() - 10
        login = AsyncMock(return_value="new")
        monkeypatch.setattr(client, "_login", login)
        await client._ensure_authenticated()
        login.assert_awaited_once()


class TestApiRequest:
    def _seeded(self, make_client, **overrides):
        client = make_client(**overrides)
        client._token = "t"
        client._token_expires = time.monotonic() + 3600
        return client

    @pytest.mark.asyncio
    async def test_http_none_raises(self, make_client):
        client = make_client()
        with pytest.raises(RuntimeError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_get_ok(self, make_client, monkeypatch):
        client = make_client()
        client._http = FakeHttp(
            [httpx.Response(200, json={"access": "t1"}), httpx.Response(200, json={"ok": 1})]
        )
        result = await client._api_request("GET", "/path", params={"a": 1})
        assert result == {"ok": 1}
        method, url, kwargs = client._http.calls[1]
        assert method == "GET"
        assert kwargs["headers"]["Authorization"] == "JWT t1"
        assert kwargs["params"] == {"a": 1}

    @pytest.mark.asyncio
    async def test_post_ok(self, make_client):
        client = make_client()
        client._http = FakeHttp(
            [httpx.Response(200, json={"access": "t1"}), httpx.Response(200, json={"ok": 1})]
        )
        result = await client._api_request("POST", "/path", params={"b": 2})
        assert result == {"ok": 1}
        assert client._http.calls[1][0] == "POST"

    @pytest.mark.asyncio
    async def test_unsupported_method(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([])
        with pytest.raises(ValueError):
            await client._api_request("PUT", "/path")

    @pytest.mark.asyncio
    async def test_transport_error_transient(self, make_client):
        client = self._seeded(make_client)

        class BoomHttp:
            async def get(self, url, **kwargs):
                raise httpx.ConnectError("net down")

        client._http = BoomHttp()
        with pytest.raises(TransientError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_404_not_found(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([httpx.Response(404)])
        with pytest.raises(NotFoundError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_401_relogin_retry(self, make_client, monkeypatch):
        client = self._seeded(make_client)

        async def fake_login():
            client._token = "fresh"
            return "fresh"

        monkeypatch.setattr(client, "_login", fake_login)
        client._http = FakeHttp([httpx.Response(401), httpx.Response(200, json={"ok": 1})])
        result = await client._api_request("GET", "/path")
        assert result == {"ok": 1}
        get_calls = [c for c in client._http.calls if c[0] == "GET"]
        assert get_calls[-1][2]["headers"]["Authorization"] == "JWT fresh"

    @pytest.mark.asyncio
    async def test_401_relogin_retry_post(self, make_client, monkeypatch):
        client = self._seeded(make_client)

        async def fake_login():
            client._token = "fresh"
            return "fresh"

        monkeypatch.setattr(client, "_login", fake_login)
        client._http = FakeHttp([httpx.Response(401), httpx.Response(200, json={"ok": 1})])
        result = await client._api_request("POST", "/path")
        assert result == {"ok": 1}
        assert client._http.calls[-1][0] == "POST"

    @pytest.mark.asyncio
    async def test_401_no_credentials_fatal(self, make_client):
        client = make_client(web_username="", web_password="")
        client._http = FakeHttp([httpx.Response(401)])
        with pytest.raises(FatalError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_429_transient(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([httpx.Response(429)])
        with pytest.raises(TransientError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_500_transient(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([httpx.Response(503)])
        with pytest.raises(TransientError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_400_fatal(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([httpx.Response(400, text="bad")])
        with pytest.raises(FatalError):
            await client._api_request("GET", "/path")

    @pytest.mark.asyncio
    async def test_retries_transient_then_succeeds(self, make_client, monkeypatch):
        client = self._seeded(make_client, max_retries=2)
        client._http = FakeHttp([httpx.Response(429), httpx.Response(200, json={"ok": 1})])
        result = await client._api_request("GET", "/path")
        assert result == {"ok": 1}
        assert len([c for c in client._http.calls if c[0] == "GET"]) == 2

    @pytest.mark.asyncio
    async def test_circuit_open_raises(self, make_client):
        client = self._seeded(make_client)
        client._http = FakeHttp([])
        client._circuit_breaker._state = "open"
        client._circuit_breaker._last_failure_time = time.monotonic()
        with pytest.raises(CircuitBreakerOpenError):
            await client._api_request("GET", "/path")


class TestFetchJson:
    @pytest.mark.asyncio
    async def test_context_none_raises(self, make_client):
        client = make_client()
        with pytest.raises(RuntimeError):
            await client._fetch_json("https://x")

    @pytest.mark.asyncio
    async def test_ok(self, make_client):
        client = make_client()
        context = FakeContext(responses=[FakeResponse(200, {"a": 1})])
        client._context = context
        result = await client._fetch_json("https://x")
        assert result == {"a": 1}
        assert client._context.pages[0].closed is True

    @pytest.mark.parametrize(
        "status,exc",
        [
            (404, NotFoundError),
            (429, TransientError),
            (500, TransientError),
            (400, FatalError),
        ],
    )
    @pytest.mark.asyncio
    async def test_error_statuses(self, make_client, status, exc):
        client = make_client()
        context = FakeContext(responses=[FakeResponse(status)])
        client._context = context
        with pytest.raises(exc):
            await client._fetch_json("https://x")

    @pytest.mark.asyncio
    async def test_none_response_transient(self, make_client):
        client = make_client()
        context = FakeContext(responses=[None])
        client._context = context
        with pytest.raises(TransientError):
            await client._fetch_json("https://x")

    @pytest.mark.asyncio
    async def test_bad_json_transient(self, make_client):
        client = make_client()
        context = FakeContext(responses=[FakeResponse(200, json_error=True)])
        client._context = context
        with pytest.raises(TransientError):
            await client._fetch_json("https://x")


class TestFetchHtml:
    @pytest.mark.asyncio
    async def test_context_none_raises(self, make_client):
        client = make_client()
        with pytest.raises(RuntimeError):
            await client._fetch_html("https://x")

    @pytest.mark.asyncio
    async def test_ok(self, make_client):
        client = make_client()
        context = FakeContext(responses=[FakeResponse(200)], page_class=FakePage)
        context.pages = []
        client._context = context
        result = await client._fetch_html("https://x")
        assert result == "<html></html>"
        assert len(client._context.pages[0].evaluate_calls) == 1
        assert client._context.pages[0].closed is True

    @pytest.mark.parametrize(
        "status,exc",
        [
            (404, NotFoundError),
            (429, TransientError),
            (500, TransientError),
            (400, FatalError),
        ],
    )
    @pytest.mark.asyncio
    async def test_error_statuses(self, make_client, status, exc):
        client = make_client()
        context = FakeContext(responses=[FakeResponse(status)])
        client._context = context
        with pytest.raises(exc):
            await client._fetch_html("https://x")

    @pytest.mark.asyncio
    async def test_none_response_transient(self, make_client):
        client = make_client()
        context = FakeContext(responses=[None])
        client._context = context
        with pytest.raises(TransientError):
            await client._fetch_html("https://x")

    @pytest.mark.asyncio
    async def test_page_content_raises_still_closes(self, make_client):
        client = make_client()

        class ExplodingPage(FakePage):
            async def content(self):
                raise RuntimeError("content boom")

        context = FakeContext(responses=[FakeResponse(200)], page_class=ExplodingPage)
        client._context = context
        with pytest.raises(RuntimeError):
            await client._fetch_html("https://x")


class TestFetchListingDispatch:
    @pytest.mark.asyncio
    async def test_legacy(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        legacy = AsyncMock(return_value=[{"a": 1}])
        monkeypatch.setattr(client, "_legacy_fetch_listing", legacy)
        result = await client.fetch_listing("USD")
        assert result == [{"a": 1}]
        legacy.assert_awaited_once_with("USD")

    @pytest.mark.asyncio
    async def test_api(self, make_client, monkeypatch):
        client = make_client()
        api = AsyncMock(return_value=[])
        monkeypatch.setattr(client, "_api_fetch_listing", api)
        result = await client.fetch_listing("USD")
        assert result == []
        api.assert_awaited_once_with("USD")


class TestLegacyFetchListing:
    @pytest.mark.asyncio
    async def test_items(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(
            client, "_fetch_json", AsyncMock(return_value={"items": [{"a": 1}, "skip"]})
        )
        result = await client._legacy_fetch_listing("USD")
        assert result == [{"a": 1}]
        assert (
            client._fetch_json.await_args.args[0] == "https://data.example.com/bonds?currency=USD"
        )

    @pytest.mark.asyncio
    async def test_data_dict(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(
            client, "_fetch_json", AsyncMock(return_value={"data": {"items": [{"b": 2}]}})
        )
        assert await client._legacy_fetch_listing("USD") == [{"b": 2}]

    @pytest.mark.asyncio
    async def test_not_found_reraises(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=NotFoundError("404")))
        with pytest.raises(NotFoundError):
            await client._legacy_fetch_listing("USD")

    @pytest.mark.asyncio
    async def test_fallback_html(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(client, "_fetch_html_cached", AsyncMock(return_value="<html>"))
        monkeypatch.setattr(
            "scraper.sources.aigenis.parsers.listing.parse_listing_html",
            lambda html, currency: [{"internal_id": "X", "currency": currency}],
        )
        result = await client._legacy_fetch_listing("USD")
        assert result == [{"internal_id": "X", "currency": "USD"}]


class TestApiFetchListing:
    @pytest.mark.asyncio
    async def test_pagination_and_filter(self, make_client, monkeypatch):
        client = make_client()
        valid_item = {"id": 1, "settl_currency": "USD", "definition": {"state_security_id": "A1"}}
        full_page = [valid_item] * 98
        full_page.append(
            {"id": 2, "settl_currency": "CNY", "definition": {"state_security_id": "C1"}}
        )
        full_page.append("not-a-dict")
        partial_page = [
            {"id": 3, "settl_currency": "USD", "definition": {"state_security_id": "A2"}}
        ]
        monkeypatch.setattr(
            client, "_api_request", AsyncMock(side_effect=[full_page, partial_page])
        )
        normalized = AsyncMock(side_effect=lambda item, currency: {"internal_id": "n"})
        monkeypatch.setattr(client, "_normalize_listing_item", normalized)
        result = await client._api_fetch_listing("USD")
        assert len(result) == 99
        assert client._id_by_internal == {"A1": 1, "A2": 3}
        assert client._api_request.call_count == 2

    @pytest.mark.asyncio
    async def test_symbol_iid_fallback(self, make_client, monkeypatch):
        client = make_client()
        item = {"id": 9, "settl_currency": "USD", "symbol": "BY/99", "definition": {}}
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=[item]))
        normalized = AsyncMock(side_effect=lambda item, currency: {"internal_id": "n"})
        monkeypatch.setattr(client, "_normalize_listing_item", normalized)
        await client._api_fetch_listing("USD")
        assert client._id_by_internal == {"99": 9}

    @pytest.mark.asyncio
    async def test_no_iid_skips(self, make_client, monkeypatch):
        client = make_client()
        item = {"id": 9, "settl_currency": "USD", "symbol": "", "definition": {}}
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=[item]))
        assert await client._api_fetch_listing("USD") == []
        assert client._id_by_internal == {}
        assert client._api_request.call_count == 1  # page smaller than 100 -> break

    @pytest.mark.asyncio
    async def test_empty_results_breaks(self, make_client, monkeypatch):
        client = make_client()
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=[]))
        assert await client._api_fetch_listing("USD") == []

    @pytest.mark.asyncio
    async def test_list_response_direct(self, make_client, monkeypatch):
        client = make_client()
        item = {"id": 5, "settl_currency": "USD", "definition": {"state_security_id": "D1"}}
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=[item]))
        normalized = AsyncMock(side_effect=lambda item, currency: {"internal_id": "n"})
        monkeypatch.setattr(client, "_normalize_listing_item", normalized)
        result = await client._api_fetch_listing("USD")
        assert len(result) == 1


class TestNormalizeListingItem:
    @pytest.mark.asyncio
    async def test_full(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=101.5))
        client = make_client()
        item = {
            "settl_currency": "USD",
            "isin": "US0001",
            "symbol": "BY/X",
            "best_bid": "99.5",
            "best_offer": "100.5",
            "market_price": "100.2",
            "name_of_security": "Name",
            "quantity": 1000,
            "definition": {
                "state_security_id": "X",
                "parent_symbol": "Parent Sym",
                "currency": "usd",
                "nominal": 1000,
                "coupon_rate": "8.5",
                "coupon_frequency": 4,
                "issue_number": "1",
                "quantity": 500,
                "income_method": "coupon",
                "available_for_individuals": True,
                "time_to_maturity_years": 3.5,
                "coupon_description": "quarterly",
                "coupon_schedule": [{"d": 1}],
                "maturity_date": "2030-01-01",
                "price": "2938.6",
                "instr_yield": "7.2",
                "issuer": {"full_name": "Issuer LLC", "logo": "/logos/logo.png"},
            },
        }
        result = await client._normalize_listing_item(item, "USD")
        assert result["internal_id"] == "X"
        assert result["name"] == "Parent Sym"
        assert result["currency"] == "USD"
        assert result["issuer_logo"] == client_mod.SITE_BASE + "/logos/logo.png"
        assert result["price"] == 101.5
        assert result["yield_to_maturity"] == Decimal("7.2")
        assert result["maturity_term_text"] == "3.5"
        assert result["fetched_at"]

    @pytest.mark.asyncio
    async def test_symbol_iid(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=100.0))
        client = make_client()
        item = {"settl_currency": "USD", "symbol": "BY/ZZ", "definition": {"currency": "usd"}}
        result = await client._normalize_listing_item(item, "USD")
        assert result["internal_id"] == "ZZ"
        assert result["name"] == "ZZ"

    @pytest.mark.asyncio
    async def test_state_security_id_with_slash(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=100.0))
        client = make_client()
        item = {
            "settl_currency": "USD",
            "symbol": "other/sym",
            "definition": {"currency": "usd", "state_security_id": "BY/K1"},
        }
        result = await client._normalize_listing_item(item, "USD")
        assert result["internal_id"] == "BY/K1"

    @pytest.mark.asyncio
    async def test_no_iid_none(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=100.0))
        client = make_client()
        item = {"settl_currency": "USD", "definition": {}}
        assert await client._normalize_listing_item(item, "USD") is None

    @pytest.mark.asyncio
    async def test_issuer_logo_variants(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=100.0))
        client = make_client()
        item = {
            "settl_currency": "USD",
            "symbol": "X/1",
            "definition": {"currency": "usd", "issuer": {"image_url": "https://cdn/logo.png"}},
        }
        result = await client._normalize_listing_item(item, "USD")
        assert result["issuer_logo"] == "https://cdn/logo.png"

    @pytest.mark.asyncio
    async def test_no_maturity_text(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=100.0))
        client = make_client()
        item = {"settl_currency": "USD", "symbol": "X/2", "definition": {"currency": "usd"}}
        result = await client._normalize_listing_item(item, "USD")
        assert result["maturity_term_text"] is None


class TestFetchDetail:
    @pytest.mark.asyncio
    async def test_legacy_dispatch(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        legacy = AsyncMock(return_value={"a": 1})
        monkeypatch.setattr(client, "_legacy_fetch_detail", legacy)
        assert await client.fetch_detail("X") == {"a": 1}

    @pytest.mark.asyncio
    async def test_api_dispatch(self, make_client, monkeypatch):
        client = make_client()
        api = AsyncMock(return_value={"a": 1})
        monkeypatch.setattr(client, "_api_fetch_detail", api)
        assert await client.fetch_detail("X") == {"a": 1}


class TestLegacyFetchDetail:
    @pytest.mark.asyncio
    async def test_ok(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(return_value={"a": 1}))
        assert await client._legacy_fetch_detail("X") == {"a": 1}

    @pytest.mark.asyncio
    async def test_not_found_reraises(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=NotFoundError("404")))
        with pytest.raises(NotFoundError):
            await client._legacy_fetch_detail("X")

    @pytest.mark.asyncio
    async def test_fallback_html(self, make_client, monkeypatch):
        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(client, "_fetch_html_cached", AsyncMock(return_value="<html>"))
        monkeypatch.setattr(
            "scraper.sources.aigenis.parsers.detail.parse_detail_html",
            lambda html, internal_id: {"internal_id": internal_id},
        )
        assert await client._legacy_fetch_detail("X") == {"internal_id": "X"}


class TestApiFetchDetail:
    @pytest.mark.asyncio
    async def test_id_missing_not_found(self, make_client):
        client = make_client()
        with pytest.raises(NotFoundError):
            await client._api_fetch_detail("UNKNOWN")

    @pytest.mark.asyncio
    async def test_non_dict_parse_error(self, make_client, monkeypatch):
        client = make_client()
        client._id_by_internal["X"] = 7
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=[1, 2]))
        with pytest.raises(ParseError):
            await client._api_fetch_detail("X")

    @pytest.mark.asyncio
    async def test_ok(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=99.9))
        client = make_client()
        client._id_by_internal["X"] = 7
        payload = {
            "symbol": "BY/X",
            "name_of_security": "Sec Name",
            "settl_currency": "usd",
            "market_price": "100.1",
            "best_bid": "99.9",
            "best_offer": "100.2",
            "calc_yield_bid": "7.1",
            "calc_yield_offer": "7.2",
            "definition": {
                "state_security_id": "X",
                "parent_symbol": "Parent",
                "currency": "USD",
                "nominal": 1000,
                "coupon_rate": "8.0",
                "coupon_frequency": 4,
                "maturity_date": "2030-06-01",
                "issue_date": "2020-01-01",
                "security_symbol": "ISIN1",
                "quantity": 5000,
                "issue_number": "2",
                "revenue_type": "coupon",
                "available_for_individuals": False,
                "time_to_maturity_years": 4.2,
                "coupon_description": "semi",
                "coupon_schedule": [{"d": 1}],
                "price": "999",
                "instr_yield": "6.9",
                "issuer": {"full_name": "Issuer SA", "logo": "/i.png"},
                "issuer_country": "BY",
                "accrued_interest_amount": "1.2",
                "available": True,
            },
        }
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=payload))
        result = await client._api_fetch_detail("X")
        assert result["internal_id"] == "X"
        assert result["name"] == "Parent"
        assert result["price"] == 99.9
        assert result["issuer_logo"] == client_mod.SITE_BASE + "/i.png"
        assert result["currency"] == "USD"
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_iid_from_symbol(self, make_client, monkeypatch):
        monkeypatch.setattr(client_mod, "_to_price_pct", AsyncMock(return_value=99.9))
        client = make_client()
        client._id_by_internal["Q"] = 7
        payload = {"symbol": "BY/QQ", "settl_currency": "USD", "definition": {"currency": "USD"}}
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=payload))
        result = await client._api_fetch_detail("Q")
        assert result["internal_id"] == "QQ"


class TestFetchHistory:
    @pytest.mark.asyncio
    async def test_legacy_items(self, make_client, monkeypatch):
        from datetime import date

        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(
            client, "_fetch_json", AsyncMock(return_value={"items": [{"d": 1}, "skip"]})
        )
        result = await client.fetch_history("X", since=date(2024, 1, 1))
        assert result == [{"d": 1}]
        url = client._fetch_json.await_args.args[0]
        assert "history?since=2024-01-01" in url

    @pytest.mark.asyncio
    async def test_legacy_items_dict(self, make_client, monkeypatch):
        from datetime import date

        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(
            client,
            "_fetch_json",
            AsyncMock(return_value={"items": {"items": [{"d": 1}, "skip"]}}),
        )
        result = await client.fetch_history("X", since=date(2024, 1, 1))
        assert result == [{"d": 1}]

    @pytest.mark.asyncio
    async def test_legacy_until_param(self, make_client, monkeypatch):
        from datetime import date

        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(return_value={"data": [{"d": 1}]}))
        result = await client.fetch_history("X", since=date(2024, 1, 1), until=date(2024, 2, 1))
        assert result == [{"d": 1}]
        assert "until=2024-02-01" in client._fetch_json.await_args.args[0]

    @pytest.mark.asyncio
    async def test_legacy_not_found_reraises(self, make_client, monkeypatch):
        from datetime import date

        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=NotFoundError("404")))
        with pytest.raises(NotFoundError):
            await client.fetch_history("X", since=date(2024, 1, 1))

    @pytest.mark.asyncio
    async def test_legacy_failure_unavailable(self, make_client, monkeypatch):
        from datetime import date

        client = make_client(data_api_url="https://data.example.com")
        monkeypatch.setattr(client, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(client, "_fetch_json", AsyncMock(side_effect=RuntimeError("boom")))
        with pytest.raises(HistoryUnavailable):
            await client.fetch_history("X", since=date(2024, 1, 1))

    @pytest.mark.asyncio
    async def test_api_mode_dispatches(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._started = True
        api = AsyncMock(return_value=[{"a": 1}])
        monkeypatch.setattr(client, "_api_fetch_history", api)
        result = await client.fetch_history("X", since=date(2024, 1, 1))
        assert result == [{"a": 1}]


class TestApiFetchHistory:
    @pytest.mark.asyncio
    async def test_empty_template(self, make_client):
        client = make_client(api_history_path="")
        with pytest.raises(HistoryUnavailable):
            await client._api_fetch_history("X", __import__("datetime").date(2024, 1, 1), None)

    @pytest.mark.asyncio
    async def test_id_missing_not_found(self, make_client):
        client = make_client()
        with pytest.raises(NotFoundError):
            await client._api_fetch_history("X", __import__("datetime").date(2024, 1, 1), None)

    @pytest.mark.asyncio
    async def test_pagination(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        big_page = {"results": [{"date": "2024-01-01", "price": 100} for _ in range(500)]}
        small_page = {"results": [{"date": "2024-01-02", "price": 101}]}
        monkeypatch.setattr(client, "_api_request", AsyncMock(side_effect=[big_page, small_page]))
        rows = await client._api_fetch_history("X", date(2024, 1, 1), None)
        assert len(rows) == 501
        assert client._api_request.await_args.kwargs["params"]["date_from"] == "2024-01-01"
        assert client._api_request.await_args.kwargs["params"]["page"] == 2

    @pytest.mark.asyncio
    async def test_404_unavailable(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        monkeypatch.setattr(client, "_api_request", AsyncMock(side_effect=NotFoundError("404")))
        with pytest.raises(HistoryUnavailable):
            await client._api_fetch_history("X", date(2024, 1, 1), None)

    @pytest.mark.asyncio
    async def test_other_error_unavailable(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        monkeypatch.setattr(client, "_api_request", AsyncMock(side_effect=RuntimeError("boom")))
        with pytest.raises(HistoryUnavailable):
            await client._api_fetch_history("X", date(2024, 1, 1), None)

    @pytest.mark.asyncio
    async def test_skips_invalid_rows(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        payload = {"results": [{"price": 100}, {"date": "2024-01-01", "price": 100}]}
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=payload))
        rows = await client._api_fetch_history("X", date(2024, 1, 1), None)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_empty_page_breaks(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        monkeypatch.setattr(client, "_api_request", AsyncMock(return_value=None))
        assert await client._api_fetch_history("X", date(2024, 1, 1), None) == []

    @pytest.mark.asyncio
    async def test_history_unavailable_passthrough(self, make_client, monkeypatch):
        from datetime import date

        client = make_client()
        client._id_by_internal["X"] = 7
        monkeypatch.setattr(
            client, "_api_request", AsyncMock(side_effect=HistoryUnavailable("nope"))
        )
        with pytest.raises(HistoryUnavailable):
            await client._api_fetch_history("X", date(2024, 1, 1), None)


class TestAigenisClientCm:
    @pytest.mark.asyncio
    async def test_context_manager(self, monkeypatch):
        started: list[str] = []
        closed: list[str] = []

        async def fake_start(self):
            started.append("s")

        async def fake_close(self):
            closed.append("c")

        monkeypatch.setattr(AigenisClient, "start", fake_start)
        monkeypatch.setattr(AigenisClient, "close", fake_close)
        async with aigenis_client() as client:
            assert isinstance(client, AigenisClient)
        assert started and closed

    @pytest.mark.asyncio
    async def test_start_failure_closes(self, monkeypatch):
        closed: list[str] = []

        async def fake_start(self):
            raise RuntimeError("boom")

        async def fake_close(self):
            closed.append("c")

        monkeypatch.setattr(AigenisClient, "start", fake_start)
        monkeypatch.setattr(AigenisClient, "close", fake_close)
        with pytest.raises(RuntimeError):
            async with aigenis_client():
                pass
        assert closed
