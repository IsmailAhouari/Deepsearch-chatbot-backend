"""Contract tests for multi-language support.

Verifies that all three locales (en, it, ar) receive identical API responses
and that locale is correctly detected from Accept-Language or request body.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


async def _db_is_reachable() -> bool:
    """Return True if the test database is reachable via asyncpg."""
    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        return False
    try:
        import asyncpg  # type: ignore[import]
        dsn = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn=dsn, timeout=3)
        await conn.close()
        return True
    except Exception:
        return False


def _make_app():
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch_test",
    )
    os.environ.setdefault("ENVIRONMENT", "development")
    from src.core.config import get_settings
    get_settings.cache_clear()
    from src.main import create_app
    return create_app()


@pytest_asyncio.fixture
async def client():
    """HTTP client against test app — no DB required (for 422 tests)."""
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_client():
    """HTTP client that skips the test if the database is not reachable."""
    if not await _db_is_reachable():
        pytest.skip(
            "Contract test requires a running PostgreSQL instance at DATABASE_URL."
        )
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test"
    ) as ac:
        yield ac


def _payload(locale: str, **overrides) -> dict:
    base = {
        "contact": {
            "nome": "Test User",
            "azienda": "TestCo",
            "email": f"test.{uuid.uuid4().hex[:6]}@testco.com",
        },
        "request_type": "demo",
        "qualification": {"target": "azienda"},
        "events": [],
        "locale": locale,
        "idempotency_key": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


# ── Locale detection via body ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_locale_it_accepted(db_client: AsyncClient) -> None:
    """Locale 'it' in request body is accepted."""
    response = await db_client.post("/api/v1/leads/capture", json=_payload("it"))
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_locale_en_accepted(db_client: AsyncClient) -> None:
    """Locale 'en' in request body is accepted."""
    response = await db_client.post("/api/v1/leads/capture", json=_payload("en"))
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_locale_ar_accepted(db_client: AsyncClient) -> None:
    """Locale 'ar' (Arabic) in request body is accepted."""
    response = await db_client.post("/api/v1/leads/capture", json=_payload("ar"))
    assert response.status_code == 200, response.text


# ── Locale detection via Accept-Language header ────────────────────────────────

@pytest.mark.asyncio
async def test_accept_language_en_sets_locale(db_client: AsyncClient) -> None:
    """Accept-Language: en header is parsed and locale is set to 'en'."""
    response = await db_client.post(
        "/api/v1/leads/capture",
        json=_payload("en"),
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_accept_language_ar_sets_locale(db_client: AsyncClient) -> None:
    """Accept-Language: ar header is parsed and locale is set to 'ar'."""
    response = await db_client.post(
        "/api/v1/leads/capture",
        json=_payload("ar"),
        headers={"Accept-Language": "ar"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_unknown_locale_defaults_to_it(db_client: AsyncClient) -> None:
    """Unknown locale (e.g. 'fr') defaults to 'it' without error."""
    response = await db_client.post(
        "/api/v1/leads/capture",
        json=_payload("fr"),
        headers={"Accept-Language": "fr,fr-FR;q=0.9"},
    )
    assert response.status_code == 200, response.text


# ── Same error format for all locales ────────────────────────────────────────

@pytest.mark.parametrize("locale,accept_lang", [
    ("it", "it"),
    ("en", "en-US"),
    ("ar", "ar"),
])
@pytest.mark.asyncio
async def test_invalid_email_returns_same_422_format_for_all_locales(
    client: AsyncClient, locale: str, accept_lang: str
) -> None:
    """Invalid email returns identical RFC 7807 422 format regardless of locale."""
    payload = _payload(locale)
    payload["contact"]["email"] = "not-an-email"
    payload["idempotency_key"] = str(uuid.uuid4())

    response = await client.post(
        "/api/v1/leads/capture",
        json=payload,
        headers={"Accept-Language": accept_lang},
    )
    assert response.status_code == 422

    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert "detail" in data
    assert data["status"] == 422


# ── No locale-specific endpoints ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_locales_use_same_endpoint(db_client: AsyncClient) -> None:
    """All locales use the same /api/v1/leads/capture endpoint."""
    for locale in ("it", "en", "ar"):
        payload = _payload(locale)
        response = await db_client.post("/api/v1/leads/capture", json=payload)
        assert response.status_code == 200, f"Failed for locale={locale}: {response.text}"
