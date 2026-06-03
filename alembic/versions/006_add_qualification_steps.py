"""Add qualification_steps to sessions.

Revision ID: 006
Revises: 208a924c7d62
Create Date: 2026-06-03

Adds:
  - sessions.qualification_steps (JSONB, nullable)
    Ordered list of qualification captures: [{screen, fields, step}]
    Preserves the sequence in which the user made selections during
    the exploratory flows, including all steps before the geo question.

Also updates the comment on sessions.qualification to reflect that
the snapshot now excludes null fields (set by the service layer, no DDL needed).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "208a924c7d62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "qualification_steps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Ordered qualification captures: [{screen, fields, step}]",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "qualification_steps")
