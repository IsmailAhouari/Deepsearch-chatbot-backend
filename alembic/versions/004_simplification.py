"""Schema simplification — remove enterprise complexity.

Revision ID: 004
Revises: 003
Create Date: 2026-06-03

Removes:
  - crm_sync_records table
  - lead_lifecycle_events table
  - qualification_profiles table
  - Columns from leads: qualification_profile_id, lifecycle_state,
    crm_sync_status, crm_lead_id, crm_sync_attempts, archived_at
  - Columns from sessions: lifecycle_state, expires_at, abandoned_at, extra_metadata
  - Adds locale column to leads

This simplification removes enterprise overhead not needed for the MVP.
The backend is a lightweight data collection service.

Note: Adding locale to leads (non-null, server_default 'it').
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Drop crm_sync_records (depends on leads) ───────────────────────────
    op.drop_index("ix_crm_sync_records_lead_id_attempted_at", table_name="crm_sync_records")
    op.drop_index("ix_crm_sync_records_status", table_name="crm_sync_records")
    op.drop_table("crm_sync_records")

    # ── 2. Drop lead_lifecycle_events (depends on leads + funnel_events) ───────
    op.drop_index(
        "ix_lead_lifecycle_events_lead_id_transitioned_at",
        table_name="lead_lifecycle_events",
    )
    op.drop_index("ix_lead_lifecycle_events_lead_id", table_name="lead_lifecycle_events")
    op.drop_table("lead_lifecycle_events")

    # ── 3. Simplify leads table ───────────────────────────────────────────────
    # Drop FK to qualification_profiles first
    op.drop_constraint("fk_leads_qualification_profile_id", "leads", type_="foreignkey")
    op.drop_index("ix_leads_lifecycle_state", table_name="leads")
    op.drop_index("ix_leads_crm_sync_status", table_name="leads")

    op.drop_constraint("ck_leads_lifecycle_state", "leads", type_="check")
    op.drop_constraint("ck_leads_crm_sync_status", "leads", type_="check")

    op.drop_column("leads", "qualification_profile_id")
    op.drop_column("leads", "lifecycle_state")
    op.drop_column("leads", "crm_sync_status")
    op.drop_column("leads", "crm_lead_id")
    op.drop_column("leads", "crm_sync_attempts")
    op.drop_column("leads", "archived_at")

    # NOTE: locale column on leads was already added by migration 003
    # (ALTER TABLE leads ADD COLUMN IF NOT EXISTS locale VARCHAR(10) DEFAULT 'it')
    # No-op here; 003 owns locale on the leads table.

    # ── 4. Drop qualification_profiles (now orphaned) ─────────────────────────
    op.drop_index(
        "ix_qualification_profiles_session_id",
        table_name="qualification_profiles",
    )
    op.drop_table("qualification_profiles")

    # ── 5. Simplify sessions table ────────────────────────────────────────────
    try:
        op.drop_constraint("ck_sessions_lifecycle_state", "sessions", type_="check")
    except Exception:
        pass  # constraint may not exist in all environments

    try:
        op.drop_index("ix_sessions_lifecycle_state", table_name="sessions")
    except Exception:
        pass
    try:
        op.drop_index("ix_sessions_expires_at", table_name="sessions")
    except Exception:
        pass

    op.drop_column("sessions", "lifecycle_state")
    op.drop_column("sessions", "expires_at")
    op.drop_column("sessions", "abandoned_at")
    op.drop_column("sessions", "extra_metadata")


def downgrade() -> None:
    """Downgrade is not supported for this migration.

    The data from removed columns/tables would need to be reconstructed
    manually. Contact the engineering team if a rollback is required.
    """
    raise NotImplementedError(
        "Downgrade from 004_simplification is not supported. "
        "Restore from backup if rollback is required."
    )
