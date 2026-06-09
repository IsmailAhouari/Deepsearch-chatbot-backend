"""Contract tests for POST /api/v1/leads/capture.

These tests verify the complete public interface behaviour:
HTTP status codes, response shapes, and error formats.

Run: pytest tests/contract/test_lead_capture.py -v
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _valid_payload(**overrides) -> dict:
    """Return a valid lead capture request payload."""
    base = {
        "contact": {
            "nome": "Mario Rossi",
            "azienda": "Acme SpA",
            "email": "mario.rossi@acme.it",
            "telefono": "+39 02 1234567",
            "ruolo": "Compliance Officer",
            "paese": "Italy",
            "note": "Interested in AML screening.",
        },
        "request_type": "demo",
        "qualification": {
            "target": "azienda",
            "obiettivo": "aml",
            "geografia": "Europa",
            "role": "compliance",
        },
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "session.started",
                "event_payload": {"source": "widget"},
                "sequence_number": 0,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "locale": "it",
            },
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "funnel.step_completed",
                "event_payload": {"step": 1, "captured_field": "target", "captured_value": "azienda"},
                "sequence_number": 1,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "locale": "it",
            },
        ],
        "metadata": {
            "session_duration_seconds": 120,
            "engagement_depth": 4,
            "source_flow": "flowB_aml",
            "visited_screens": ["welcome", "flowB", "flowB_aml"],
            "intent_signals": {"aml": 3},
        },
        "locale": "it",
        "idempotency_key": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


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


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client connected to the test app (no auth required)."""
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch_test",
    )
    os.environ.setdefault("ENVIRONMENT", "development")

    from src.core.config import get_settings
    get_settings.cache_clear()

    from src.main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client that skips the test if the database is not reachable.

    Use this fixture for tests that expect 200 responses requiring DB writes.
    Tests using the plain ``client`` fixture still run (e.g. 422 validation tests).
    """
    if not await _db_is_reachable():
        pytest.skip(
            "Contract test requires a running PostgreSQL instance at DATABASE_URL. "
            "Set DATABASE_URL to a reachable DB to run these tests."
        )
    import os
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch_test",
    )
    from src.core.config import get_settings
    get_settings.cache_clear()
    from src.main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capture_returns_200_with_session_and_lead_ids(db_client: AsyncClient) -> None:
    """Full valid payload returns 200 with session_id and lead_id UUIDs."""
    payload = _valid_payload()
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text

    data = response.json()
    assert "session_id" in data
    assert "lead_id" in data
    uuid.UUID(data["session_id"])
    uuid.UUID(data["lead_id"])
    assert data["status"] == "captured"


@pytest.mark.asyncio
async def test_capture_returns_x_request_id_header(db_client: AsyncClient) -> None:
    """Response includes X-Request-ID header."""
    response = await db_client.post("/api/v1/leads/capture", json=_valid_payload())
    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_capture_with_minimal_contact_fields(db_client: AsyncClient) -> None:
    """Capture succeeds with only the three required contact fields."""
    payload = _valid_payload()
    payload["contact"] = {
        "nome": "Giulia Bianchi",
        "azienda": "TestCo",
        "email": "giulia@testco.it",
    }
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_capture_with_empty_qualification(db_client: AsyncClient) -> None:
    """Capture succeeds when qualification has all null fields (partial funnel)."""
    payload = _valid_payload()
    payload["qualification"] = {}
    payload["idempotency_key"] = str(uuid.uuid4())
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text


# ── Backward compat shim ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capture_accepts_legacy_qualification_field_names(db_client: AsyncClient) -> None:
    """Old frontend field names are mapped to canonical names."""
    payload = _valid_payload()
    payload["qualification"] = {
        "subject_type": "azienda",
        "motivation": "aml",
        "country": "Europa",
        "user_role": "compliance",
    }
    payload["idempotency_key"] = str(uuid.uuid4())
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text


# ── Validation errors (422) ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_nome_returns_422(client: AsyncClient) -> None:
    """Missing required `nome` field returns 422 with field-level error."""
    payload = _valid_payload()
    payload["contact"] = {"azienda": "Acme", "email": "test@test.it"}
    payload["idempotency_key"] = str(uuid.uuid4())
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text

    data = response.json()
    assert data["status"] == 422
    errors = data.get("errors", [])
    field_names = [e["field"] for e in errors]
    assert any("nome" in f for f in field_names), f"Expected 'nome' in errors, got: {field_names}"


@pytest.mark.asyncio
async def test_invalid_email_returns_422(client: AsyncClient) -> None:
    """Invalid email address returns 422 with field-level error on `email`."""
    payload = _valid_payload()
    payload["contact"] = {"nome": "Test", "azienda": "TestCo", "email": "not-an-email"}
    payload["idempotency_key"] = str(uuid.uuid4())
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text

    data = response.json()
    errors = data.get("errors", [])
    field_names = [e["field"] for e in errors]
    assert any("email" in f for f in field_names), f"Expected 'email' in errors, got: {field_names}"


@pytest.mark.asyncio
async def test_missing_request_type_returns_422(client: AsyncClient) -> None:
    """Missing required `request_type` returns 422 with field-level error."""
    payload = _valid_payload()
    payload.pop("request_type", None)  # ensure absent regardless of helper defaults
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text

    data = response.json()
    errors = data.get("errors", [])
    field_names = [e["field"] for e in errors]
    assert any("request_type" in f for f in field_names), (
        f"Expected 'request_type' in errors, got: {field_names}"
    )


@pytest.mark.asyncio
async def test_invalid_request_type_returns_422(client: AsyncClient) -> None:
    """An unrecognised `request_type` value returns 422."""
    payload = _valid_payload(request_type="meeting")
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text

    data = response.json()
    errors = data.get("errors", [])
    field_names = [e["field"] for e in errors]
    assert any("request_type" in f for f in field_names), (
        f"Expected 'request_type' in errors, got: {field_names}"
    )


@pytest.mark.asyncio
async def test_null_request_type_returns_422(client: AsyncClient) -> None:
    """Explicit null `request_type` returns 422 (None is not a valid Request Type)."""
    payload = _valid_payload(request_type=None)
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("request_type", ["demo", "contact", "generic_request"])
@pytest.mark.asyncio
async def test_all_valid_request_types_accepted(
    client: AsyncClient, request_type: str
) -> None:
    """All three valid Request Type values are accepted by the schema."""
    payload = _valid_payload(request_type=request_type)
    # Use client (no DB) — we only need schema validation to pass, not persistence
    response = await client.post("/api/v1/leads/capture", json=payload)
    # 503 (DB unreachable) is acceptable here; 422 is not
    assert response.status_code != 422, (
        f"request_type='{request_type}' was rejected: {response.text}"
    )


@pytest.mark.asyncio
async def test_missing_contact_object_returns_422(client: AsyncClient) -> None:
    """Missing entire `contact` object returns 422."""
    payload = _valid_payload()
    del payload["contact"]
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_empty_body_returns_422(client: AsyncClient) -> None:
    """Empty request body returns 422."""
    response = await client.post(
        "/api/v1/leads/capture",
        content=b"",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422, response.text


# ── Idempotency ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_existing_lead(db_client: AsyncClient) -> None:
    """Submitting the same idempotency_key twice returns the same lead_id."""
    idempotency_key = str(uuid.uuid4())
    payload = _valid_payload()
    payload["idempotency_key"] = idempotency_key

    r1 = await db_client.post("/api/v1/leads/capture", json=payload)
    assert r1.status_code == 200, r1.text

    r2 = await db_client.post("/api/v1/leads/capture", json=payload)
    assert r2.status_code == 200, r2.text

    assert r1.json()["lead_id"] == r2.json()["lead_id"]
    assert r1.json()["session_id"] == r2.json()["session_id"]


# ── Frontend contract ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capture_accepts_note_at_root_level(db_client: AsyncClient) -> None:
    """DemoForm.jsx sends `note` at the root of the payload."""
    payload = {
        "contact": {
            "nome": "Test User",
            "azienda": "TestCo",
            "email": "test@testco.it",
        },
        "request_type": "contact",
        "qualification": {
            "subject_type": "azienda",
            "motivation": "due_diligence",
            "country": "Europa",
            "user_role": "legal",
        },
        "metadata": {
            "session_duration_seconds": 90,
            "engagement_depth": 5,
        },
        "note": "This note comes from the root level of the payload",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_capture_accepts_exact_demoform_payload_shape(db_client: AsyncClient) -> None:
    """Validate the exact payload shape that DemoForm.jsx currently submits."""
    payload = {
        "contact": {
            "nome": "Mario Rossi",
            "azienda": "ACME SpA",
            "email": "mario@acme.it",
            "telefono": "",
            "ruolo": "Compliance Officer",
            "paese": "Italia",
        },
        "request_type": "demo",
        "qualification": {
            "subject_type": "azienda",
            "motivation": "due diligence",
            "request_nature": "verifica societaria",
            "func_role": None,
            "country": "Europa",
            "user_role": "legal",
            "need_type": None,
            "source_flow": "flowB_dd",
        },
        "metadata": {
            "source": "deepsearch_chatbot_widget",
            "session_duration_seconds": 180,
            "engagement_depth": 7,
        },
        "note": "Nota aggiuntiva dal form",
        "idempotency_key": str(uuid.uuid4()),
    }
    response = await db_client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, (
        f"DemoForm.jsx payload shape rejected: {response.status_code} {response.text}"
    )


# ── Error response format ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_422_response_follows_rfc7807(client: AsyncClient) -> None:
    """All 422 responses have RFC 7807 problem detail format."""
    payload = _valid_payload()
    del payload["contact"]
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422

    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert "detail" in data
    assert data["status"] == 422


# ── Health endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    """GET /health always returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert data["status"] in ("healthy", "degraded")
    assert "version" in data
