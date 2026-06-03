"""FunnelEvent ORM model — append-only audit log of every user action.

Events are the source of truth for analytics. They must never be deleted.
`event_id` is a client-supplied UUID used for idempotency deduplication.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class FunnelEvent(UUIDMixin, Base):
    """Single auditable event emitted during a visitor session.

    No `updated_at` — events are immutable after insert.
    """

    __tablename__ = "funnel_events"

    __table_args__ = (
        UniqueConstraint(
            "session_id", "sequence_number",
            name="uq_funnel_events_session_sequence",
        ),
        UniqueConstraint(
            "event_id",
            name="uq_funnel_events_event_id",
        ),
        Index("ix_funnel_events_session_id", "session_id"),
        Index("ix_funnel_events_lead_id", "lead_id"),
        Index("ix_funnel_events_event_type", "event_type"),
        Index("ix_funnel_events_occurred_at", "occurred_at"),
    )

    # ── Idempotency key ───────────────────────────────────────────────────────
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        comment="Client-generated UUID for idempotency; must be stable across retries",
    )

    # ── Foreign keys ──────────────────────────────────────────────────────────
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
        comment="Populated after lead creation",
    )

    # ── Event content ─────────────────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    event_payload: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'it'"),
    )

    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ── Insert audit ──────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session",
        back_populates="funnel_events",
        lazy="raise",
    )

    lead: Mapped["Lead | None"] = relationship(  # noqa: F821
        "Lead",
        back_populates="funnel_events",
        foreign_keys=[lead_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<FunnelEvent id={self.id!s:.8} "
            f"type={self.event_type} seq={self.sequence_number}>"
        )
