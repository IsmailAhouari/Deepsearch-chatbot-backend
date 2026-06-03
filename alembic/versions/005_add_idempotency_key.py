"""Add idempotency_key to leads — idempotent submission support.

Revision ID: 005
Revises: 004
Create Date: 2026-06-03

Adds:
  - leads.idempotency_key (UUID, nullable)
  - Partial unique index: ix_leads_idempotency_key WHERE idempotency_key IS NOT NULL

A partial unique index is used rather than a UNIQUE column constraint so that
multiple leads submitted WITHOUT an idempotency_key (NULL) are not conflated
(NULL != NULL in SQL). Only non-null keys are deduplicated.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "idempotency_key",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Client-supplied UUID for idempotent submission; unique when not NULL",
        ),
    )

    # Partial unique index: enforces uniqueness only for non-null keys.
    op.execute(
        "CREATE UNIQUE INDEX ix_leads_idempotency_key "
        "ON leads (idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_leads_idempotency_key")
    op.drop_column("leads", "idempotency_key")
