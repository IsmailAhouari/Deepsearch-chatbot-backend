"""Initial schema — all 6 tables for DeepSearch v1.

Revision ID: 001
Revises: (none)
Create Date: 2026-05-29

Tables created:
  sessions              — anonymous visitor sessions
  qualification_profiles — canonical funnel answers
  funnel_events          — append-only event log
  leads                  — commercial PII records
  lead_lifecycle_events  — state-transition audit log
  crm_sync_records       — CRM push attempt log

Upgrade creates all tables, FK constraints, check constraints, indexes,
and the updated_at trigger function.
Downgrade drops all tables in reverse FK dependency order.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enable pgcrypto for gen_random_uuid() ────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── updated_at trigger function ───────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # ── sessions ──────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("locale", sa.String(10), server_default=sa.text("'it'"), nullable=False),
        sa.Column(
            "lifecycle_state",
            sa.String(20),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("source_flow", sa.String(50), nullable=True),
        sa.Column("engagement_depth", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("visited_screens", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("intent_signals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("session_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("extra_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("abandoned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('active', 'abandoned', 'converted')",
            name="ck_sessions_lifecycle_state",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])
    op.create_index("ix_sessions_lifecycle_state", "sessions", ["lifecycle_state"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.execute("""
        CREATE TRIGGER set_sessions_updated_at
        BEFORE UPDATE ON sessions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── qualification_profiles ────────────────────────────────────────────────
    op.create_table(
        "qualification_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target", sa.String(50), nullable=True),
        sa.Column("obiettivo", sa.String(100), nullable=True),
        sa.Column("geografia", sa.String(100), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("extra_qualification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
            name="fk_qualification_profiles_session_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_qualification_profiles_session_id",
        "qualification_profiles",
        ["session_id"],
    )

    op.execute("""
        CREATE TRIGGER set_qualification_profiles_updated_at
        BEFORE UPDATE ON qualification_profiles
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── leads ─────────────────────────────────────────────────────────────────
    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("qualification_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Contact PII
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("azienda", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("telefono", sa.String(50), nullable=True),
        sa.Column("ruolo", sa.String(100), nullable=True),
        sa.Column("paese", sa.String(100), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        # Qualification snapshot
        sa.Column("target", sa.String(50), nullable=True),
        sa.Column("obiettivo", sa.String(100), nullable=True),
        sa.Column("geografia", sa.String(100), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("extra_qualification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_qualification", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Lifecycle & CRM
        sa.Column(
            "lifecycle_state",
            sa.String(30),
            server_default=sa.text("'new'"),
            nullable=False,
        ),
        sa.Column(
            "crm_sync_status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("crm_lead_id", sa.String(255), nullable=True),
        sa.Column("crm_sync_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('new', 'qualified', 'demo_requested', "
            "'contacted', 'converted', 'disqualified')",
            name="ck_leads_lifecycle_state",
        ),
        sa.CheckConstraint(
            "crm_sync_status IN ('pending', 'synced', 'failed', 'skipped')",
            name="ck_leads_crm_sync_status",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="RESTRICT",
            name="fk_leads_session_id",
        ),
        sa.ForeignKeyConstraint(
            ["qualification_profile_id"],
            ["qualification_profiles.id"],
            ondelete="RESTRICT",
            name="fk_leads_qualification_profile_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_leads_session_id"),
    )
    op.create_index("ix_leads_session_id", "leads", ["session_id"])
    op.create_index("ix_leads_lifecycle_state", "leads", ["lifecycle_state"])
    op.create_index("ix_leads_crm_sync_status", "leads", ["crm_sync_status"])
    op.create_index("ix_leads_created_at", "leads", ["created_at"])
    op.create_index("ix_leads_email", "leads", ["email"])

    op.execute("""
        CREATE TRIGGER set_leads_updated_at
        BEFORE UPDATE ON leads
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ── funnel_events ─────────────────────────────────────────────────────────
    op.create_table(
        "funnel_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("locale", sa.String(10), server_default=sa.text("'it'"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            ondelete="CASCADE",
            name="fk_funnel_events_session_id",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            ondelete="SET NULL",
            name="fk_funnel_events_lead_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_funnel_events_event_id"),
        sa.UniqueConstraint(
            "session_id",
            "sequence_number",
            name="uq_funnel_events_session_sequence",
        ),
    )
    op.create_index("ix_funnel_events_session_id", "funnel_events", ["session_id"])
    op.create_index("ix_funnel_events_lead_id", "funnel_events", ["lead_id"])
    op.create_index("ix_funnel_events_event_type", "funnel_events", ["event_type"])
    op.create_index("ix_funnel_events_occurred_at", "funnel_events", ["occurred_at"])

    # ── lead_lifecycle_events ─────────────────────────────────────────────────
    op.create_table(
        "lead_lifecycle_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggering_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_state", sa.String(30), nullable=True),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column(
            "transitioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            ondelete="CASCADE",
            name="fk_lead_lifecycle_events_lead_id",
        ),
        sa.ForeignKeyConstraint(
            ["triggering_event_id"],
            ["funnel_events.id"],
            ondelete="SET NULL",
            name="fk_lead_lifecycle_events_triggering_event_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_lead_lifecycle_events_lead_id_transitioned_at",
        "lead_lifecycle_events",
        ["lead_id", "transitioned_at"],
    )
    op.create_index(
        "ix_lead_lifecycle_events_lead_id",
        "lead_lifecycle_events",
        ["lead_id"],
    )

    # ── crm_sync_records ──────────────────────────────────────────────────────
    op.create_table(
        "crm_sync_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("crm_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'synced', 'failed', 'skipped')",
            name="ck_crm_sync_records_status",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            ondelete="CASCADE",
            name="fk_crm_sync_records_lead_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_crm_sync_records_lead_id_attempted_at",
        "crm_sync_records",
        ["lead_id", "attempted_at"],
    )
    op.create_index("ix_crm_sync_records_status", "crm_sync_records", ["status"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("crm_sync_records")
    op.drop_table("lead_lifecycle_events")
    op.drop_table("funnel_events")
    op.drop_table("leads")
    op.drop_table("qualification_profiles")
    op.drop_table("sessions")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
