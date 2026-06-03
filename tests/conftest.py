"""Shared pytest fixtures and configuration.

This file is loaded automatically by pytest before running any tests.
"""
from __future__ import annotations

import os

import pytest


def pytest_configure(config) -> None:
    """Set test environment variables before any test module is imported.

    Force-set (not setdefault) all vars that affect Settings construction so
    that stale values from .env or the shell environment never bleed into tests.

    CORS_ORIGINS must be a JSON array string because pydantic-settings v2
    calls json.loads() on list[str] fields before field validators run.
    A bare comma-separated string like "http://a,http://b" is NOT valid JSON
    and will raise SettingsError at startup.
    """
    # Required — asyncpg URL
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch_test",
    )
    # Force-set these so stale .env values don't bleed in
    os.environ["ENVIRONMENT"] = "development"
    os.environ["LOG_LEVEL"] = "WARNING"  # reduce noise in test output
    os.environ["CRM_ADAPTER_CLASS"] = "src.integrations.crm.null_adapter.NullAdapter"
    # JSON array — required by pydantic-settings v2 for list[str] env fields
    os.environ["CORS_ORIGINS"] = '["https://deepsearchch-chatbot-frontend.vercel.app"]'


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Reset the in-memory rate limiter storage before each test.

    The SlowAPI Limiter is a module-level singleton with an in-memory counter.
    Without this fixture, request counts from earlier tests bleed into later
    ones and trigger 429 responses on what should be successful test requests.

    slowapi stores counters in limits.storage.MemoryStorage which exposes
    a reset() method that clears all hit counts.
    """
    try:
        from src.middleware.rate_limit import limiter
        storage = getattr(limiter, "_storage", None)
        if storage is not None and hasattr(storage, "reset"):
            storage.reset()
    except Exception:
        pass  # If the module hasn't been imported yet, nothing to reset


@pytest.fixture(autouse=True)
def reset_db_engine() -> None:
    """Force a fresh SQLAlchemy engine for every test.

    The engine and session factory are module-level globals in
    src.core.database.  pytest-asyncio creates a NEW event loop for every
    test function.  Asyncpg connections are bound to the event loop that
    created them; reusing them across loops produces:

        'NoneType' object has no attribute 'send'   (asyncpg _protocol = None)
        RuntimeError: Event loop is closed           (during pool teardown)

    Resetting the globals here (synchronously, before the test's event loop
    is created) guarantees that every test that touches the DB creates a
    completely fresh engine + connection pool in its own loop.

    Any connections owned by the previous engine are orphaned; PostgreSQL
    will clean them up via its idle-connection timeout.
    """
    try:
        import src.core.database as db_module
        db_module._engine = None
        db_module._session_factory = None
    except Exception:
        pass  # Module not imported yet — nothing to reset
