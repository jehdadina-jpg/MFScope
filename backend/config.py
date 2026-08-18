"""
Centralised settings — loaded once, imported everywhere.
Uses pydantic-settings so every value can be overridden by an env var or a .env file.
"""
from functools import lru_cache
from pydantic import AnyUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./mfscope.db"

    # ── API security ──────────────────────────────────────────────────────────
    secret_key: str = "dev-secret-change-me"
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # ── AMFI feeds ───────────────────────────────────────────────────────────
    amfi_nav_url: str = "https://www.amfiindia.com/spages/NAVAll.txt"
    amfi_scheme_url: str = "https://api.mfapi.in/mf"

    # ── News RSS ──────────────────────────────────────────────────────────────
    et_markets_rss: str = "https://economictimes.indiatimes.com/markets/rss"
    moneycontrol_rss: str = "https://www.moneycontrol.com/rss/MCtopnews.xml"
    livemint_rss: str = "https://www.livemint.com/rss/markets"
    business_standard_rss: str = "https://www.business-standard.com/rss/markets-106.rss"

    # ── NLP ───────────────────────────────────────────────────────────────────
    sentiment_model: str = "ProsusAI/finbert"
    sentiment_backend: str = "finbert"  # "finbert" | "vader"

    # ── Scheduler ────────────────────────────────────────────────────────────
    nav_pull_interval_seconds: int = 86400
    news_pull_interval_seconds: int = 3600

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",")]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
