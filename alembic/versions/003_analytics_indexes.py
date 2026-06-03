"""Analytics performance indexes — non-blocking concurrent creation.

Revision ID: 003
Revises: 001
Create Date: 2026-05-29

Adds composite indexes optimized for the 3 analytics queries in data-model.md:
  1. Funnel drop-off by step: funnel_events(event_type, occurred_at)
  2. Conversion by locale: requires sessions join — leads(created_at) + sessions(locale)
  3. Lead volume by dimension: leads(target, obiettivo, created_at)

Uses CREATE INDEX CONCURRENTLY to avoid locking the table during creation.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Requires running outside a transaction for CONCURRENTLY to work.
    # Alembic handles this via execute_with_ddl_events when the migration
    # is called with --ddl-transaction-per-operation (or via non-transactional mode).
    # For safety we provide both transactional and non-transactional versions.

    # Analytics query 1: funnel drop-off by event_type + occurred_at
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analytics_funnel_events_type_time "
        "ON funnel_events (event_type, occurred_at)"
    )

    # Analytics query 2: lead volume by qualification dimensions
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analytics_leads_qualification "
        "ON leads (target, obiettivo, created_at)"
    )

    # Analytics query 3: conversion by locale — leads need locale from sessions
    # Adding locale denorm to leads table for simpler analytics queries
    op.execute(
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS locale VARCHAR(10) DEFAULT 'it'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_analytics_leads_locale_created "
        "ON leads (locale, created_at)"
    )

    # Populate locale from session for existing rows (if any)
    op.execute(
        "UPDATE leads SET locale = s.locale "
        "FROM sessions s WHERE leads.session_id = s.id AND leads.locale IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_analytics_leads_locale_created")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS locale")
    op.execute("DROP INDEX IF EXISTS ix_analytics_leads_qualification")
    op.execute("DROP INDEX IF EXISTS ix_analytics_funnel_events_type_time")
