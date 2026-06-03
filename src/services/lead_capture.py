"""Lead capture service — atomic transaction for the capture flow.

A single database transaction atomically creates:
  1. Session  — anonymous visitor record (no PII)
  2. Lead     — commercial record with PII + qualification snapshot
  3. FunnelEvents — event log from the request

Idempotency: if a Lead already exists for the same session (determined by
the unique constraint on leads.session_id), the existing Lead is returned
without creating duplicates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger, RequestContext
from src.models.event import FunnelEvent
from src.models.lead import Lead
from src.models.session import Session
from src.schemas.lead_capture import LeadCaptureRequest, LeadCaptureResponse

logger = get_logger(__name__)


async def capture_lead(
    db: AsyncSession,
    request: LeadCaptureRequest,
) -> LeadCaptureResponse:
    """Atomically capture a qualified lead from a demo request submission.

    All database writes happen within a single transaction. If any write
    fails the entire operation is rolled back — no partial data is stored.

    Args:
        db: Database session. The caller is responsible for the transaction
            context (typically `get_db` dependency which commits on success).
        request: Validated lead capture request.

    Returns:
        LeadCaptureResponse with session_id, lead_id, and created_at.
    """
    # 0. Idempotency check ────────────────────────────────────────────────────
    # If the client supplied an idempotency_key and we already have a lead for
    # that key, return the existing lead immediately without any DB writes.
    if request.idempotency_key is not None:
        existing_result = await db.execute(
            select(Lead).where(Lead.idempotency_key == request.idempotency_key)
        )
        existing_lead = existing_result.scalar_one_or_none()
        if existing_lead is not None:
            logger.info(
                "lead_capture_idempotent_key",
                lead_id=str(existing_lead.id),
                session_id=str(existing_lead.session_id),
            )
            return LeadCaptureResponse(
                session_id=existing_lead.session_id,
                lead_id=existing_lead.id,
                created_at=existing_lead.created_at,
            )

    # 1. Create session ────────────────────────────────────────────────────────
    meta = request.metadata
    session = Session(
        locale=request.locale,
        source_flow=meta.source_flow if meta else None,
        engagement_depth=(meta.engagement_depth or 0) if meta else 0,
        visited_screens=meta.visited_screens if meta else None,
        intent_signals=meta.intent_signals if meta else None,
        session_duration_seconds=meta.session_duration_seconds if meta else None,
        qualification=request.qualification.model_dump(mode="python", exclude_none=False),
    )
    db.add(session)
    await db.flush()  # get server-assigned UUID

    # Update request context for logging (after session ID is available)
    RequestContext.set(
        request_id=RequestContext.get().get("request_id", ""),
        session_id=str(session.id),
        endpoint="/api/v1/leads/capture",
        locale=request.locale,
    )

    # 2. Create Lead ──────────────────────────────────────────────────────────
    contact = request.contact
    extra_qual = request.qualification.get_extra_qualification()
    raw_payload = request.qualification.model_dump(mode="python", exclude_none=False)

    lead_values = {
        "session_id": session.id,
        "idempotency_key": request.idempotency_key,
        # Contact PII (NEVER log these fields)
        "nome": contact.nome,
        "azienda": contact.azienda,
        "email": str(contact.email),
        "telefono": contact.telefono,
        "ruolo": contact.ruolo,
        "paese": contact.paese,
        "note": request.resolved_note,
        # Qualification snapshot
        "target": request.qualification.target,
        "obiettivo": request.qualification.obiettivo,
        "geografia": request.qualification.geografia,
        "role": request.qualification.role,
        "locale": request.locale,
        "extra_qualification": extra_qual if extra_qual else None,
        "raw_qualification": raw_payload,
    }

    insert_stmt = (
        pg_insert(Lead)
        .values(**lead_values)
        .on_conflict_do_nothing(constraint="uq_leads_session_id")
        .returning(Lead.id, Lead.created_at)
    )

    result = await db.execute(insert_stmt)
    row = result.first()

    if row is None:
        # Conflict — lead already exists for this session; fetch the existing one
        existing = await db.execute(
            select(Lead).where(Lead.session_id == session.id)
        )
        existing_lead = existing.scalar_one()
        logger.info(
            "lead_capture_idempotent",
            session_id=str(session.id),
            lead_id=str(existing_lead.id),
        )
        return LeadCaptureResponse(
            session_id=existing_lead.session_id,
            lead_id=existing_lead.id,
            created_at=existing_lead.created_at,
        )

    lead_id: uuid.UUID = row[0]
    lead_created_at: datetime = row[1]

    # 3. Persist funnel events ────────────────────────────────────────────────
    if request.events:
        await _persist_events(
            db=db,
            session_id=session.id,
            lead_id=lead_id,
            events=request.events,
        )

    await db.flush()

    logger.info(
        "lead_captured",
        session_id=str(session.id),
        lead_id=str(lead_id),
        locale=request.locale,
        event_count=len(request.events),
        has_qualification=any([
            request.qualification.target,
            request.qualification.obiettivo,
            request.qualification.geografia,
            request.qualification.role,
        ]),
    )

    return LeadCaptureResponse(
        session_id=session.id,
        lead_id=lead_id,
        created_at=lead_created_at,
    )


async def _persist_events(
    db: AsyncSession,
    session_id: uuid.UUID,
    lead_id: uuid.UUID,
    events: list,
) -> None:
    """Persist events with idempotency deduplication via ON CONFLICT DO NOTHING."""
    from datetime import timezone as tz
    values = []
    for event in events:
        occurred_at = event.occurred_at
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=tz.utc)
        values.append({
            "event_id": event.event_id,
            "session_id": session_id,
            "lead_id": lead_id,
            "event_type": event.event_type,
            "event_payload": event.event_payload,
            "locale": event.locale or "it",
            "sequence_number": event.sequence_number,
            "occurred_at": occurred_at,
        })

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(FunnelEvent).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=["event_id"])
    await db.execute(stmt)
