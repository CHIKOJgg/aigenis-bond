from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Currency = Literal["USD", "BYN", "EUR", "RUB", "XAU", "XAG", "XPT", "CNY"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGENIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    base_url: str = "https://aigenis.by"
    web_url: str = "https://web.aigenis.by"
    web_username: str = ""
    web_password: str = ""
    data_api_url: str | None = None
    # API-mode history endpoint template ({id} = internal security id). Defaults
    # to the invest.aigenis.by market-data endpoint; override if the API path
    # differs. Set empty to disable history collection in API mode.
    api_history_path: str = "/v1/security_history/{id}/"

    headless: bool = True
    use_stealth: bool = True
    delay_between_requests: float = 2.0
    max_concurrency: int = 2
    max_retries: int = 3
    timeout: int = 30
    browser_health_interval_s: int = 300

    ignore_https_errors: bool = False

    currencies_raw: str = Field(default="", validation_alias="AIGENIS_CURRENCIES")

    @property
    def currencies(self) -> list[Currency]:
        if not self.currencies_raw.strip():
            return ["USD", "BYN", "EUR", "XAU", "XAG", "XPT", "CNY"]
        import json as _json

        try:
            return _json.loads(self.currencies_raw)
        except (_json.JSONDecodeError, TypeError):
            pass
        return [c.strip().upper() for c in self.currencies_raw.split(",") if c.strip()]

    history_backfill_days: int = 1825

    # Cron expression for the full bond scrape (Europe/Minsk). 11:00 MSK / 08:00 UTC once per day.
    scrape_all_cron: str = "0 11 * * *"

    log_level: str = "INFO"
    log_file: str = "logs/scraper.log"
    log_json: bool = True
    log_rotation: str = "100 MB"
    log_retention: str = "14 days"

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    sentry_dsn: str | None = None
    environment: str = "production"

    # Deployment profile: "saas" (current B2C) | "aigenis" (B2B integration).
    # Profile "aigenis" forbids browser scraping (fail-closed) and relies on the
    # official data feed via MarketDataProvider (plan item 5.7).
    deployment_profile: str = Field(default="saas", validation_alias="DEPLOYMENT_PROFILE")
    # Active market-data provider: aigenis_official | moex | demo_fixtures.
    # Configurable provider selection (plan item 5.5).
    data_provider: str = Field(default="", validation_alias="DATA_PROVIDER")

    # License/contract id для lineage snapshots (plan item 5.6).
    license_contract_id: str | None = Field(
        default=None, validation_alias="AIGENIS_LICENSE_CONTRACT_ID"
    )

    # Google OAuth client id used to verify the `aud`/`azp` claim of Google
    # id_tokens during the /auth/google login flow. If unset, Google login is
    # disabled.
    google_client_id: str | None = Field(default=None, validation_alias="GOOGLE_CLIENT_ID")

    @field_validator("delay_between_requests")
    @classmethod
    def _validate_delay(cls, v: float) -> float:
        if v < 0:
            return 0.0
        return v

    @field_validator("max_concurrency")
    @classmethod
    def _validate_concurrency(cls, v: int) -> int:
        # A 0/negative value would create an asyncio.Semaphore that blocks every
        # pipeline task forever — clamp to a sane minimum instead of failing.
        return max(v, 1)

    @field_validator("max_retries")
    @classmethod
    def _validate_retries(cls, v: int) -> int:
        # 0 retries means tenacity fails instantly on the first transient error.
        return max(v, 1)

    @field_validator("currencies_raw")
    @classmethod
    def _validate_currencies_raw(cls, v: str) -> str:
        # Unknown currency strings from env would silently flow into the
        # pipeline and pollute the currency column — fail fast instead.
        allowed = {"USD", "BYN", "EUR", "RUB", "XAU", "XAG", "XPT", "CNY"}
        import json as _json

        try:
            parsed = _json.loads(v) if v.strip() else []
            if isinstance(parsed, list):
                raw_items = [str(x).strip().upper() for x in parsed]
            else:
                raw_items = [x.strip().upper() for x in v.split(",") if x.strip()]
        except (_json.JSONDecodeError, TypeError):
            raw_items = [x.strip().upper() for x in v.split(",") if x.strip()]
        bad = [c for c in raw_items if c not in allowed]
        if bad:
            raise ValueError(
                f"Unknown currencies in AIGENIS_CURRENCIES: {', '.join(bad)}. "
                f"Allowed: {', '.join(sorted(allowed))}"
            )
        return v

    @field_validator("history_backfill_days")
    @classmethod
    def _validate_backfill_days(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 3650:
            return 3650
        return v

    @property
    def user_agent_short(self) -> str:
        return self.user_agent.split("/")[0] if "/" in self.user_agent else self.user_agent

    def log_file_path(self) -> Path:
        p = Path(self.log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(default="sqlite+aiosqlite:///:memory:", validation_alias="DATABASE_URL")
    url_sync: str = Field(default="", validation_alias="DATABASE_URL_SYNC")
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: float = 30.0
    pool_recycle: int = 3600
    slow_query_threshold_s: float = 0.1
    echo: bool = False
    max_retries: int = 3
    retry_delay: float = 1.0


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    retry_on_timeout: bool = True
    max_connections: int = 20
    health_check_interval: int = 30


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    bot_username: str = Field(default="", validation_alias="TELEGRAM_BOT_USERNAME")
    alert_chat_id: str = Field(default="", validation_alias="TELEGRAM_ALERT_CHAT_ID")
    admin_ids_raw: str = Field(default="", validation_alias="TELEGRAM_ADMIN_IDS")

    @property
    def admin_ids(self) -> list[int]:
        if not self.admin_ids_raw.strip():
            return []
        import json as _json

        try:
            parsed = _json.loads(self.admin_ids_raw)
            if isinstance(parsed, list):
                return [int(x) for x in parsed]
        except (_json.JSONDecodeError, TypeError, ValueError):
            pass
        # Fall back to comma-separated ints; a garbage value must not crash
        # startup, so non-numeric entries are skipped.
        out: list[int] = []
        for x in self.admin_ids_raw.split(","):
            x = x.strip()
            if not x:
                continue
            try:
                out.append(int(x))
            except ValueError:
                continue
        return out

    webhook_url: str = Field(default="", validation_alias="WEBHOOK_URL")
    webhook_path: str = Field(default="/webhook", validation_alias="WEBHOOK_PATH")
    webhook_port: int = Field(default=8080, validation_alias="WEBHOOK_PORT")
    rate_limit_per_sec: int = 3
    rate_limit_window: int = 1


class StockSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STOCK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = True
    data_source: str = "moex"
    boards_raw: str = ""
    history_backfill_days: int = 730
    refresh_cadence_min: int = 30
    error_budget: int = 3

    @property
    def boards(self) -> list[str]:
        raw = self.boards_raw.strip()
        if raw:
            return [b.strip().upper() for b in raw.split(",") if b.strip()]
        return ["TQBR", "TQOD", "TQDE"]

    @field_validator("history_backfill_days")
    @classmethod
    def _validate_history_days(cls, v: int) -> int:
        if v < 1:
            return 1
        if v > 3650:
            return 3650
        return v

    @field_validator("refresh_cadence_min")
    @classmethod
    def _validate_cadence(cls, v: int) -> int:
        if v < 1:
            return 1
        return v

    @field_validator("error_budget")
    @classmethod
    def _validate_error_budget(cls, v: int) -> int:
        return max(v, 1)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    aigenis: Settings = Field(default_factory=Settings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    stock: StockSettings = Field(default_factory=StockSettings)

    debug: bool = False

    def validate_all(self) -> list[str]:
        warnings: list[str] = []
        if self.aigenis.data_api_url and not self.aigenis.data_api_url.startswith("http"):
            warnings.append("AIGENIS_DATA_API_URL should start with http")
        if not self.telegram.bot_token:
            warnings.append("TELEGRAM_BOT_TOKEN is not set — bot will not work")
        return warnings


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def reload_settings() -> AppSettings:
    global _settings
    _settings = AppSettings()
    return _settings
