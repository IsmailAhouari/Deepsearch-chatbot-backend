"""Unit tests for settings and configuration validation.

Tests verify that standard database connection strings (postgres://, postgresql://)
are dynamically rewritten to the required asyncpg format.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_database_url_preserves_asyncpg(monkeypatch):
    """Valid postgresql+asyncpg:// URLs are preserved as-is."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://usr:pwd@host:5432/db")
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://usr:pwd@host:5432/db"


def test_database_url_rewrites_standard_postgresql(monkeypatch):
    """Standard postgresql:// URLs are rewritten to include the asyncpg driver."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://usr:pwd@host:5432/db")
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://usr:pwd@host:5432/db"


def test_database_url_rewrites_standard_postgres(monkeypatch):
    """Standard postgres:// URLs (e.g. from Heroku/Railway) are rewritten to include asyncpg."""
    monkeypatch.setenv("DATABASE_URL", "postgres://usr:pwd@host:5432/db")
    settings = Settings()
    assert settings.database_url == "postgresql+asyncpg://usr:pwd@host:5432/db"


def test_database_url_raises_validation_error_on_invalid_scheme(monkeypatch):
    """Invalid database schemes raise a ValidationError."""
    monkeypatch.setenv("DATABASE_URL", "sqlite:///mydb.db")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    assert "DATABASE_URL must be a valid PostgreSQL connection string" in str(exc_info.value)


# ── Production startup validation ─────────────────────────────────────────────

class TestProductionEmailStartupValidation:
    """In production, all three email config vars are required at startup."""

    _DB = "postgresql+asyncpg://test:test@localhost/test"

    def _full_prod_env(self, monkeypatch) -> None:
        monkeypatch.setenv("DATABASE_URL", self._DB)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("RESEND_API_KEY", "re_live_key")
        monkeypatch.setenv("CALENDLY_EVENT_URL", "https://calendly.com/deepsearch/demo")
        monkeypatch.setenv("INSIDE_NOTIFICATION_EMAIL", "inside@deepsearch.ch")

    def test_production_succeeds_when_all_email_vars_present(self, monkeypatch):
        """Settings loads without error when all three vars are set in production."""
        self._full_prod_env(monkeypatch)
        settings = Settings()
        assert settings.is_production

    def test_production_fails_when_resend_api_key_missing(self, monkeypatch):
        """Missing RESEND_API_KEY in production raises ValidationError at startup."""
        self._full_prod_env(monkeypatch)
        monkeypatch.delenv("RESEND_API_KEY")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "RESEND_API_KEY" in str(exc_info.value)

    def test_production_fails_when_calendly_event_url_missing(self, monkeypatch):
        """Missing CALENDLY_EVENT_URL in production raises ValidationError at startup."""
        self._full_prod_env(monkeypatch)
        monkeypatch.delenv("CALENDLY_EVENT_URL")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "CALENDLY_EVENT_URL" in str(exc_info.value)

    def test_production_fails_when_inside_notification_email_missing(self, monkeypatch):
        """Missing INSIDE_NOTIFICATION_EMAIL in production raises ValidationError at startup."""
        self._full_prod_env(monkeypatch)
        monkeypatch.delenv("INSIDE_NOTIFICATION_EMAIL")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "INSIDE_NOTIFICATION_EMAIL" in str(exc_info.value)

    def test_production_error_lists_all_missing_vars(self, monkeypatch):
        """Error message names every missing var when multiple are absent."""
        monkeypatch.setenv("DATABASE_URL", self._DB)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("CALENDLY_EVENT_URL", raising=False)
        monkeypatch.delenv("INSIDE_NOTIFICATION_EMAIL", raising=False)
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        error_text = str(exc_info.value)
        assert "RESEND_API_KEY" in error_text
        assert "CALENDLY_EVENT_URL" in error_text
        assert "INSIDE_NOTIFICATION_EMAIL" in error_text

    def test_development_starts_without_email_vars(self, monkeypatch):
        """Settings loads cleanly in development even when all email vars are absent."""
        monkeypatch.setenv("DATABASE_URL", self._DB)
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("CALENDLY_EVENT_URL", raising=False)
        monkeypatch.delenv("INSIDE_NOTIFICATION_EMAIL", raising=False)
        settings = Settings()
        assert settings.is_development

    def test_staging_starts_without_email_vars(self, monkeypatch):
        """Settings loads cleanly in staging even when all email vars are absent."""
        monkeypatch.setenv("DATABASE_URL", self._DB)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("CALENDLY_EVENT_URL", raising=False)
        monkeypatch.delenv("INSIDE_NOTIFICATION_EMAIL", raising=False)
        settings = Settings()
        assert settings.environment == "staging"
