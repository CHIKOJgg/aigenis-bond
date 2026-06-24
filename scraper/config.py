from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Currency = Literal["USD", "BYN", "EUR", "XAU", "XAG", "XPT"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGENIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    base_url: str = "https://aigenis.by"
    data_api_url: str | None = None

    headless: bool = True
    use_stealth: bool = True
    delay_between_requests: float = 2.0
    max_concurrency: int = 2
    max_retries: int = 3
    timeout: int = 30

    currencies: list[Currency] = Field(
        default_factory=lambda: ["USD", "BYN", "EUR", "XAU", "XAG", "XPT"]
    )

    history_backfill_days: int = 1825

    log_level: str = "INFO"
    log_file: str = "logs/scraper.log"

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    def log_file_path(self) -> Path:
        p = Path(self.log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
