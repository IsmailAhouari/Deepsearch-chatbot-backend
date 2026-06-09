"""Unit tests for lead capture qualification assembly.

These exercise the pure `build_extra_qualification` seam with real request
objects — no DB, no mocks. End-to-end persistence is covered by
tests/integration/test_lead_persistence.py.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

from src.schemas.lead_capture import LeadCaptureRequest
from src.services.lead_capture import build_extra_qualification


def _request(**overrides) -> LeadCaptureRequest:
    base = {
        "contact": {"nome": "Mario", "azienda": "Acme", "email": "m@acme.it"},
        "request_type": "demo",
        "qualification": {"target": "azienda", "obiettivo": "aml"},
    }
    base.update(overrides)
    return LeadCaptureRequest(**base)


def test_extra_qualification_includes_request_type():
    """The submitted request_type is captured in the qualification overflow."""
    extra = build_extra_qualification(_request(request_type="demo"))
    assert extra is not None
    assert extra["request_type"] == "demo"


def test_extra_qualification_round_trips_all_request_types():
    """All three Request Type values are captured."""
    for rt in ("demo", "contact", "generic_request"):
        extra = build_extra_qualification(_request(request_type=rt))
        assert extra["request_type"] == rt


def test_extra_qualification_preserves_flow_specific_extras():
    """Non-canonical qualification fields are kept alongside request_type."""
    req = _request(
        request_type="contact",
        qualification={"target": "azienda", "func_role": "legal", "need_type": "kyc"},
    )
    extra = build_extra_qualification(req)
    assert extra["request_type"] == "contact"
    assert extra["func_role"] == "legal"
    assert extra["need_type"] == "kyc"
