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
