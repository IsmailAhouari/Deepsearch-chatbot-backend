"""Lead ORM model — the commercial record created at form submission.

A Lead is created when the visitor submits the demo request form.
It contains:
  - Contact PII (nome, azienda, email, telefono, ruolo, paese, note)
  - Qualification snapshot (canonical fields + raw_qualification JSONB)
  - Session linkage

SECURITY: This model contains PII. Fields marked with # PII must never be
logged in structured log output.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class Lead(UUIDMixin, TimestampMixin, Base):
    """Commercial lead record — contains PII and qualification snapshot."""

    __tablename__ = "leads"

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_leads_session_id"),
        Index("ix_leads_session_id", "session_id"),
        Index("ix_leads_created_at", "created_at"),
        Index("ix_leads_email", "email"),
        # Partial unique index: one lead per idempotency_key (when provided).
        # Using a partial index keeps the constraint NULL-safe (nulls are not equal
        # to each other in SQL, so a plain unique column would not deduplicate).
        Index(
            "ix_leads_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where="idempotency_key IS NOT NULL",
        ),
    )

    # ── Idempotency ───────────────────────────────────────────────────────────
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Client-supplied UUID for idempotent submission; unique when not NULL",
    )

    # ── Foreign keys ──────────────────────────────────────────────────────────
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        comment="One lead per session",
    )

    # ── Contact PII ───────────────────────────────────────────────────────────
    # PII — must never appear in application logs
    nome: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PII: full name of the contact",
    )  # PII

    azienda: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PII: company / organisation name",
    )  # PII

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        comment="PII: contact email address",
    )  # PII

    telefono: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="PII: phone number",
    )  # PII

    ruolo: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="PII: job title / role description (free text from form)",
    )  # PII

    paese: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Country of the contact",
    )

    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="PII: additional notes from the lead",
    )  # PII

    # ── Qualification snapshot ─────────────────────────────────────────────────
    target: Mapped[str | None] = mapped_column(String(50), nullable=True)
    obiettivo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    geografia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(10), nullable=True)

    extra_qualification: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Non-canonical qualification overflow",
    )

    raw_qualification: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Verbatim qualification payload as submitted. Immutable.",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    session: Mapped["Session"] = relationship(  # noqa: F821
        "Session",
        back_populates="lead",
        lazy="raise",
    )

    funnel_events: Mapped[list["FunnelEvent"]] = relationship(  # noqa: F821
        "FunnelEvent",
        back_populates="lead",
        foreign_keys="[FunnelEvent.lead_id]",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id!s:.8}>"
