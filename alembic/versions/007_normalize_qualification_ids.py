"""Normalize qualification display strings to locale-neutral IDs.

Revision ID: 007
Revises: 006
Create Date: 2026-06-12

Historical rows in leads.obiettivo and leads.role contain Italian display
strings captured before issue-019 normalized the frontend flow files.
This migration converts them to the same canonical IDs the frontend now writes.

leads.target is included for completeness; historically it was already
lowercased by the frontend (.toLowerCase()), so no rows should match.

Idempotent: rows already containing a canonical ID are not touched.
Rollback: downgrade() reverses every mapping exactly.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Canonical mapping tables ──────────────────────────────────────────────────
# Keys are the Italian display strings stored by the pre-019 frontend.
# Values are the locale-neutral IDs now written by buildLeadPayload.js.
# Must stay in sync with FLOW_IDS / capture.value in the frontend flow files.

TARGET_MAP: dict[str, str] = {
    "Aziende": "aziende",
    "Persone": "persone",
}

OBIETTIVO_MAP: dict[str, str] = {
    "Due Diligence":          "due_diligence",
    "Analisi AML":            "aml",
    "Analisi del rischio":    "risk_analysis",
    "Selezione partner affari": "partner_selection",
    "Verifica fornitori":     "supplier_check",
    "Litigation intelligence":"litigation",
    "Rischio reputazionale":  "reputational_risk",
    "Assunzione dipendente":  "hiring",
    "Altro":                  "other",
}

ROLE_MAP: dict[str, str] = {
    "Security / Risk":    "security_risk",
    "Legale / Contenzioso": "legal",
    "Compliance / AML":   "compliance_aml",
    "Direzione / Board":  "management",
    "Investitore / Fondo":"investor",
    "Altro":              "other",
}


# ── Core logic — pure functions, testable without Alembic context ─────────────

def _normalize_column(conn, table: str, column: str, mapping: dict[str, str]) -> None:
    for old_val, new_val in mapping.items():
        conn.execute(
            text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),
            {"new": new_val, "old": old_val},
        )


def _apply_normalization(conn) -> None:
    _normalize_column(conn, "leads", "target",    TARGET_MAP)
    _normalize_column(conn, "leads", "obiettivo", OBIETTIVO_MAP)
    _normalize_column(conn, "leads", "role",      ROLE_MAP)
    conn.commit()


def _revert_normalization(conn) -> None:
    _normalize_column(conn, "leads", "target",    {v: k for k, v in TARGET_MAP.items()})
    _normalize_column(conn, "leads", "obiettivo", {v: k for k, v in OBIETTIVO_MAP.items()})
    _normalize_column(conn, "leads", "role",      {v: k for k, v in ROLE_MAP.items()})
    conn.commit()


# ── Alembic entry points ──────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()
    _apply_normalization(conn)


def downgrade() -> None:
    conn = op.get_bind()
    _revert_normalization(conn)
