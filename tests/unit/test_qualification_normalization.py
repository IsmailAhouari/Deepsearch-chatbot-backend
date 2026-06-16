"""TDD — Qualification ID normalization migration (issue-019 backend).

Tests run against an in-memory SQLite database so no PostgreSQL connection
is required. The migration logic under test is _apply_normalization() and
_revert_normalization() — pure functions that accept a SQLAlchemy connection.
"""
from __future__ import annotations

import pytest
from sqlalchemy import Column, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase


# ── Minimal in-memory schema ──────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def make_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE leads ("
            "  id TEXT PRIMARY KEY,"
            "  target TEXT,"
            "  obiettivo TEXT,"
            "  role TEXT"
            ")"
        ))
        conn.commit()
    return engine


def insert_lead(conn, id: str, target=None, obiettivo=None, role=None):
    conn.execute(
        text("INSERT INTO leads (id, target, obiettivo, role) VALUES (:id, :t, :o, :r)"),
        {"id": id, "t": target, "o": obiettivo, "r": role},
    )
    conn.commit()


def get_lead(conn, id: str) -> dict:
    row = conn.execute(text("SELECT target, obiettivo, role FROM leads WHERE id = :id"), {"id": id}).fetchone()
    return {"target": row[0], "obiettivo": row[1], "role": row[2]}


# ── Import migration helpers — RED until the migration file exists ─────────────
import importlib.util, pathlib

_migration_path = (
    pathlib.Path(__file__).parents[2]
    / "alembic" / "versions" / "007_normalize_qualification_ids.py"
)
_spec = importlib.util.spec_from_file_location("migration_007", _migration_path)
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

_apply_normalization = _migration._apply_normalization
_revert_normalization = _migration._revert_normalization
OBIETTIVO_MAP = _migration.OBIETTIVO_MAP
ROLE_MAP = _migration.ROLE_MAP
TARGET_MAP = _migration.TARGET_MAP


# ── Cycle 1 — tracer bullet ───────────────────────────────────────────────────

class TestTracerBullet:
    def test_due_diligence_normalized_to_id(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "1", obiettivo="Due Diligence")
            _apply_normalization(conn)
            lead = get_lead(conn, "1")
        assert lead["obiettivo"] == "due_diligence"


# ── Cycle 2 — full obiettivo mapping ─────────────────────────────────────────

class TestObiettivoMapping:
    @pytest.mark.parametrize("italian,expected_id", OBIETTIVO_MAP.items())
    def test_obiettivo_normalized(self, italian, expected_id):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, italian, obiettivo=italian)
            _apply_normalization(conn)
            lead = get_lead(conn, italian)
        assert lead["obiettivo"] == expected_id


# ── Cycle 3 — full role mapping ───────────────────────────────────────────────

class TestRoleMapping:
    @pytest.mark.parametrize("italian,expected_id", ROLE_MAP.items())
    def test_role_normalized(self, italian, expected_id):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, italian, role=italian)
            _apply_normalization(conn)
            lead = get_lead(conn, italian)
        assert lead["role"] == expected_id


# ── Cycle 4 — target mapping (safety net) ────────────────────────────────────

class TestTargetMapping:
    @pytest.mark.parametrize("italian,expected_id", TARGET_MAP.items())
    def test_target_normalized(self, italian, expected_id):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, italian, target=italian)
            _apply_normalization(conn)
            lead = get_lead(conn, italian)
        assert lead["target"] == expected_id


# ── Cycle 5 — null values are untouched ──────────────────────────────────────

class TestNullHandling:
    def test_null_obiettivo_unchanged(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "null-row", obiettivo=None)
            _apply_normalization(conn)
            lead = get_lead(conn, "null-row")
        assert lead["obiettivo"] is None

    def test_already_normalized_value_unchanged(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "already-done", obiettivo="due_diligence")
            _apply_normalization(conn)
            lead = get_lead(conn, "already-done")
        assert lead["obiettivo"] == "due_diligence"


# ── Cycle 6 — idempotency ─────────────────────────────────────────────────────

class TestIdempotency:
    def test_running_migration_twice_is_safe(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "1", obiettivo="Analisi AML", role="Security / Risk")
            _apply_normalization(conn)
            _apply_normalization(conn)  # second run — must not error or corrupt
            lead = get_lead(conn, "1")
        assert lead["obiettivo"] == "aml"
        assert lead["role"] == "security_risk"


# ── Cycle 7 — rollback (downgrade) ───────────────────────────────────────────

class TestRollback:
    def test_downgrade_reverses_obiettivo(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "1", obiettivo="Analisi AML")
            _apply_normalization(conn)
            assert get_lead(conn, "1")["obiettivo"] == "aml"
            _revert_normalization(conn)
            assert get_lead(conn, "1")["obiettivo"] == "Analisi AML"

    def test_downgrade_reverses_role(self):
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "1", role="Legale / Contenzioso")
            _apply_normalization(conn)
            assert get_lead(conn, "1")["role"] == "legal"
            _revert_normalization(conn)
            assert get_lead(conn, "1")["role"] == "Legale / Contenzioso"

    def test_downgrade_on_already_clean_db_is_safe(self):
        """Downgrade on a DB with no Italian strings does nothing harmful."""
        engine = make_engine()
        with engine.connect() as conn:
            insert_lead(conn, "1", obiettivo="due_diligence", role="legal")
            _revert_normalization(conn)
            # 'due_diligence' → 'Due Diligence' (this IS expected from the reverse map)
            lead = get_lead(conn, "1")
        assert lead["obiettivo"] == "Due Diligence"
        assert lead["role"] == "Legale / Contenzioso"


# ── Cycle 8 — mapping completeness matches frontend ──────────────────────────

class TestMappingCompleteness:
    """Verify the DB mapping dict covers every value the frontend flow files
    normalize. This test is a contract between frontend and backend — if a
    new capture.value is added to the flows, this test forces a DB mapping entry."""

    FRONTEND_OBIETTIVO_IDS = {
        "due_diligence", "aml", "risk_analysis", "partner_selection",
        "supplier_check", "litigation", "reputational_risk", "hiring", "other",
    }
    FRONTEND_ROLE_IDS = {
        "security_risk", "legal", "compliance_aml", "management", "investor",
        "hr", "other",
    }
    FRONTEND_TARGET_IDS = {"aziende", "persone"}

    def test_obiettivo_map_covers_all_frontend_ids(self):
        assert set(OBIETTIVO_MAP.values()) >= self.FRONTEND_OBIETTIVO_IDS

    def test_role_map_covers_all_frontend_ids(self):
        # hr is not in ROLE_MAP (it was already 'hr' historically — no display string variant)
        covered = set(ROLE_MAP.values()) | {"hr"}
        assert covered >= self.FRONTEND_ROLE_IDS

    def test_target_map_covers_all_frontend_ids(self):
        assert set(TARGET_MAP.values()) >= self.FRONTEND_TARGET_IDS
