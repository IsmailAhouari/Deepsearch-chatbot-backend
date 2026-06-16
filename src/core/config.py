"""Application configuration loaded from environment variables.

Uses pydantic-settings for validated, fail-fast loading.
Any missing required variable raises ValueError at startup — no silent defaults.

Authentication: none. The only client is the DeepSearch frontend (HTTPS + CORS).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application configuration sourced from environment variables.

    Required fields have no default — startup fails immediately with a clear
    error message if any variable is absent or invalid.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Treat empty-string env vars as absent so field defaults apply.
        # This prevents SettingsError when CORS_ORIGINS="" or similar.
        env_ignore_empty=True,
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str
    """asyncpg connection string, e.g. postgresql+asyncpg://user:pass@host/db"""

    # ── CRM ───────────────────────────────────────────────────────────────────
    crm_adapter_class: str = "src.integrations.crm.null_adapter.NullAdapter"
    """Dotted import path of the CRM adapter class to load at startup."""

    crm_api_key: str | None = None
    """API key for the configured CRM provider (if applicable)."""

    # ── Booking (Cal.com) ────────────────────────────────────────────────────
    booking_event_url: str | None = None
    """Cal.com event type URL (e.g. https://cal.com/yourname/deepsearch-demo).
    Booking links are built by appending pre-fill query params — no API key needed."""

    # ── Email (Resend) ────────────────────────────────────────────────────────
    resend_api_key: str | None = None
    """Resend API key for transactional emails (optional)."""

    inside_notification_email: str | None = None
    """Recipient address for Operator Notification emails (Commercial Team inbox)."""

    email_from_address: str | None = None
    """Sender address for all outbound emails. Required in production; must be a
    Resend-verified domain. No default ships — production startup fails if unset."""

    # ── Application ───────────────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    """Runtime environment — controls log format and debug behaviour."""

    cors_origins: list[str] = ["https://deepsearchch-chatbot-frontend.vercel.app"]
    """Comma-separated list of allowed CORS origins (frontend widget URLs)."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    """Minimum log level emitted by structlog."""

    port: int = 8000
    """Port the uvicorn server listens on (Railway injects this automatically)."""

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    # ── Validators ────────────────────────────────────────────────────────────
    @model_validator(mode="after")
    def require_email_config_in_production(self) -> "Settings":
        """Fail fast in production when any email integration var is absent.

        In development/staging the vars remain optional — the email service
        degrades gracefully with warning logs.
        """
        if self.environment != "production":
            return self

        missing = [
            name
            for name, value in [
                ("RESEND_API_KEY", self.resend_api_key),
                ("BOOKING_EVENT_URL", self.booking_event_url),
                ("INSIDE_NOTIFICATION_EMAIL", self.inside_notification_email),
                ("EMAIL_FROM_ADDRESS", self.email_from_address),
            ]
            if not value
        ]

        if missing:
            raise ValueError(
                f"Required in production but not configured: {', '.join(missing)}. "
                "Set these environment variables before deploying."
            )
        return self

    @field_validator("database_url", mode="before")
    @classmethod
    def database_url_must_be_asyncpg(cls, v: str) -> str:
        if not isinstance(v, str):
            return v
        # Support standard postgres:// or postgresql:// and automatically prepend +asyncpg
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must be a valid PostgreSQL connection string "
                "(e.g., postgresql:// or postgresql+asyncpg://)"
            )
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Accept a comma-separated string or an already-decoded list.

        NOTE: pydantic-settings v2 calls json.loads() on list[str] env fields
        before this validator runs.  Set CORS_ORIGINS as a JSON array in .env:
            CORS_ORIGINS=["https://deepsearchch-chatbot-frontend.vercel.app"]
        A bare comma-separated value is NOT valid JSON and will raise
        SettingsError before this validator is reached.
        """
        if isinstance(v, str):
            # Fallback for programmatic use — not triggered from env.
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached application settings.

    Called once at startup; subsequent calls return the cached instance.
    The cache can be cleared in tests via get_settings.cache_clear().
    """
    return Settings()
