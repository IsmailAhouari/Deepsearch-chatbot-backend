"""Session ORM model — represents a visitor interaction.

A Session is created atomically with the Lead at form submission.
It holds behavioural metadata but NO PII. PII lives exclusively in Lead.
"""
from __future__ import annotations

from sqlalchemy import (
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class Session(UUIDMixin, TimestampMixin, Base):
    """Anonymous visitor session — no PII stored here."""

    __tablename__ = "sessions"

    __table_args__ = (
        Index("ix_sessions_created_at", "created_at"),
    )

    # ── Core fields ───────────────────────────────────────────────────────────
    locale: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="it",
        server_default=text("'it'"),
        comment="BCP-47 locale tag (en / it / ar)",
    )

    source_flow: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Which frontend flow triggered the capture (e.g. flowB_aml)",
    )

    # ── Engagement metadata ───────────────────────────────────────────────────
    engagement_depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Number of distinct screens visited",
    )

    visited_screens: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered list of screen IDs visited during the session",
    )

    intent_signals: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Map of intent_type → visit_count accumulated during exploration",
    )

    session_duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Wall-clock duration from first screen to capture submission",
    )

    qualification: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Verbatim qualification snapshot copied from the lead request",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    funnel_events: Mapped[list["FunnelEvent"]] = relationship(  # noqa: F821
        "FunnelEvent",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="raise",
    )

    lead: Mapped["Lead | None"] = relationship(  # noqa: F821
        "Lead",
        back_populates="session",
        uselist=False,
        lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<Session id={self.id!s:.8} locale={self.locale}>"
