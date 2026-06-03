"""Integration tests for lead capture persistence.

These tests run against a REAL PostgreSQL database (not mocked).
They verify that:
  - sessions, leads, and funnel_events are written atomically
  - Zero data loss for all qualification fields
  - Null fields are stored as NULL (not dropped or coerced)
  - Non-canonical fields land in extra_qualification JSONB
  - Duplicate idempotency_key produces exactly one Lead row
  - Invalid email fails before any DB write
  - Legacy frontend field names are mapped to canonical columns

Requires: a running PostgreSQL instance at DATABASE_URL.
Run: pytest tests/integration/ -v --asyncio-mode=auto
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func

from src.core.database import get_session_factory


def _payload(**overrides) -> dict:
    base = {
        "contact": {
            "nome": "Test User",
            "azienda": "Test Corp",
            "email": "test@testcorp.it",
            "telefono": "+39 02 999 999",
            "ruolo": "Analyst",
            "paese": "Italy",
            "note": "Integration test note.",
        },
        "qualification": {
            "target": "azienda",
            "obiettivo": "due_diligence",
            "geografia": "Europa",
            "role": "legal",
        },
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "session.started",
                "event_payload": {"source": "test"},
                "sequence_number": 0,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "locale": "it",
            },
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "funnel.step_completed",
                "event_payload": {
                    "step": 1,
                    "captured_field": "target",
                    "captured_value": "azienda",
                },
                "sequence_number": 1,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "locale": "it",
            },
        ],
        "metadata": {
            "session_duration_seconds": 90,
            "engagement_depth": 3,
            "source_flow": "flowB",
            "visited_screens": ["welcome", "flowB"],
            "intent_signals": {"due_diligence": 2},
        },
        "locale": "it",
        "idempotency_key": str(uuid.uuid4()),
    }
    base.update(overrides)
    return base


@pytest_asyncio.fixture
async def client():
    """HTTP client against test app; skips if DB is not reachable."""
    import os
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        pytest.skip("Integration tests require DATABASE_URL pointing to a real DB")

    # Verify DB is reachable
    try:
        from sqlalchemy import text
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Integration tests require a running PostgreSQL instance at DATABASE_URL")

    from src.main import create_app
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Direct DB session for verification queries."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


# ── All-fields persistence ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_capture_persists_session_lead_and_events(client, db_session) -> None:
    """Full capture persists sessions, leads, and funnel_events tables."""
    payload = _payload()
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200, response.text

    data = response.json()
    session_id = uuid.UUID(data["session_id"])
    lead_id = uuid.UUID(data["lead_id"])

    # Verify sessions table
    from src.models.session import Session
    s = await db_session.get(Session, session_id)
    assert s is not None
    assert s.locale == "it"
    assert s.source_flow == "flowB"
    assert s.engagement_depth == 3
    assert s.session_duration_seconds == 90
    assert s.visited_screens == ["welcome", "flowB"]
    assert s.qualification == payload["qualification"]

    # Verify leads table
    from src.models.lead import Lead
    lead = await db_session.get(Lead, lead_id)
    assert lead is not None
    assert lead.target == "azienda"
    assert lead.obiettivo == "due_diligence"
    assert lead.geografia == "Europa"
    assert lead.role == "legal"
    assert lead.locale == "it"
    assert lead.raw_qualification is not None

    # Verify funnel_events table
    from src.models.event import FunnelEvent
    result = await db_session.execute(
        select(FunnelEvent)
        .where(FunnelEvent.session_id == session_id)
        .order_by(FunnelEvent.sequence_number)
    )
    events = list(result.scalars().all())
    assert len(events) == 2
    assert events[0].event_type == "session.started"
    assert events[1].event_type == "funnel.step_completed"
    assert events[0].lead_id == lead_id


@pytest.mark.asyncio
async def test_null_obiettivo_stored_as_null_not_dropped(client, db_session) -> None:
    """Partial qualification with null obiettivo stores NULL — not dropped."""
    payload = _payload()
    payload["qualification"] = {"target": "persona"}  # only target
    payload["idempotency_key"] = str(uuid.uuid4())

    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200

    lead_id = uuid.UUID(response.json()["lead_id"])

    from src.models.lead import Lead
    lead = await db_session.get(Lead, lead_id)
    assert lead.target == "persona"
    assert lead.obiettivo is None    # NOT dropped, stored as NULL
    assert lead.geografia is None
    assert lead.role is None


@pytest.mark.asyncio
async def test_unknown_qual_field_stored_in_extra_qualification(client, db_session) -> None:
    """Non-canonical qualification field lands in extra_qualification JSONB."""
    payload = _payload()
    payload["qualification"] = {
        "target": "azienda",
        "obiettivo": "aml",
        "func_role": "investigator",
        "need_type": "enhanced_due_diligence",
    }
    payload["idempotency_key"] = str(uuid.uuid4())

    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200

    lead_id = uuid.UUID(response.json()["lead_id"])

    from src.models.lead import Lead
    lead = await db_session.get(Lead, lead_id)
    assert lead.target == "azienda"
    assert lead.obiettivo == "aml"
    assert lead.extra_qualification is not None
    assert lead.extra_qualification.get("func_role") == "investigator"
    assert lead.extra_qualification.get("need_type") == "enhanced_due_diligence"


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_single_lead(client, db_session) -> None:
    """Duplicate submission produces exactly one Lead row in DB."""
    idempotency_key = str(uuid.uuid4())
    payload = _payload()
    payload["idempotency_key"] = idempotency_key

    r1 = await client.post("/api/v1/leads/capture", json=payload)
    r2 = await client.post("/api/v1/leads/capture", json=payload)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["lead_id"] == r2.json()["lead_id"]

    # Only one Lead row in DB
    from src.models.lead import Lead
    session_id = uuid.UUID(r1.json()["session_id"])
    count_result = await db_session.execute(
        select(func.count(Lead.id)).where(Lead.session_id == session_id)
    )
    count = count_result.scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_invalid_email_returns_422_before_db_write(client, db_session) -> None:
    """Invalid email format returns 422 with zero DB writes."""
    from src.models.lead import Lead

    count_before = (await db_session.execute(select(func.count(Lead.id)))).scalar_one()

    payload = _payload()
    payload["contact"]["email"] = "not-valid-email"
    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 422

    count_after = (await db_session.execute(select(func.count(Lead.id)))).scalar_one()
    assert count_before == count_after, "DB was written despite validation failure"


@pytest.mark.asyncio
async def test_legacy_field_names_mapped_to_canonical(client, db_session) -> None:
    """Legacy field names (subject_type, etc.) are stored in canonical columns."""
    payload = _payload()
    payload["qualification"] = {
        "subject_type": "azienda",
        "motivation": "hiring",
        "country": "Italia",
        "user_role": "hr",
    }
    payload["idempotency_key"] = str(uuid.uuid4())

    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200

    lead_id = uuid.UUID(response.json()["lead_id"])
    from src.models.lead import Lead
    lead = await db_session.get(Lead, lead_id)

    assert lead.target == "azienda"    # subject_type → target
    assert lead.obiettivo == "hiring"  # motivation → obiettivo
    assert lead.geografia == "Italia"  # country → geografia
    assert lead.role == "hr"           # user_role → role


@pytest.mark.asyncio
async def test_root_level_note_persisted_correctly(client, db_session) -> None:
    """Note sent at root level is persisted on the Lead."""
    payload = _payload()
    payload["note"] = "Root level note from DemoForm.jsx"
    payload["contact"].pop("note", None)  # no note in contact
    payload["idempotency_key"] = str(uuid.uuid4())

    response = await client.post("/api/v1/leads/capture", json=payload)
    assert response.status_code == 200

    lead_id = uuid.UUID(response.json()["lead_id"])
    from src.models.lead import Lead
    lead = await db_session.get(Lead, lead_id)
    assert lead.note == "Root level note from DemoForm.jsx"
