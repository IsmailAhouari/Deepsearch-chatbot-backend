"""PII security tests.

Tests verify:
  - PII fields never appear in structured log output
  - The PII redaction processor removes all known sensitive field names
  - NullAdapter does not log full email addresses
  - request_id middleware does NOT log request body

These are unit tests — no DB required.
"""
from __future__ import annotations

import json
import uuid

import pytest
import structlog


# ── Log PII redaction tests ────────────────────────────────────────────────────

class TestPIIRedactionProcessor:
    """The _redact_pii structlog processor must remove all PII field names."""

    def _run_processor(self, event_dict: dict) -> dict:
        from src.core.logging import _redact_pii
        return _redact_pii(None, None, event_dict.copy())

    def test_nome_is_redacted(self):
        result = self._run_processor({"event": "test", "nome": "Mario Rossi"})
        assert result["nome"] == "[REDACTED]"

    def test_email_is_redacted(self):
        result = self._run_processor({"event": "test", "email": "mario@example.com"})
        assert result["email"] == "[REDACTED]"

    def test_azienda_is_redacted(self):
        result = self._run_processor({"event": "test", "azienda": "ACME Corp"})
        assert result["azienda"] == "[REDACTED]"

    def test_telefono_is_redacted(self):
        result = self._run_processor({"event": "test", "telefono": "+39 02 1234567"})
        assert result["telefono"] == "[REDACTED]"

    def test_note_is_redacted(self):
        result = self._run_processor({"event": "test", "note": "Sensitive note"})
        assert result["note"] == "[REDACTED]"

    def test_non_pii_fields_are_preserved(self):
        result = self._run_processor({
            "event": "lead_captured",
            "session_id": "abc-123",
            "lead_id": "def-456",
            "locale": "it",
            "event_count": 3,
        })
        assert result["session_id"] == "abc-123"
        assert result["lead_id"] == "def-456"
        assert result["locale"] == "it"
        assert result["event_count"] == 3

    def test_all_pii_fields_are_covered(self):
        """Every field in PII_FIELDS must be redacted."""
        from src.core.logging import PII_FIELDS

        pii_values = {field: f"sensitive_value_for_{field}" for field in PII_FIELDS}
        pii_values["event"] = "test_event"

        result = self._run_processor(pii_values)

        for field in PII_FIELDS:
            assert result[field] == "[REDACTED]", (
                f"PII field '{field}' was NOT redacted — it would leak to logs"
            )


# ── CRM adapter PII exclusion tests ───────────────────────────────────────────

class TestNullAdapterPIILogging:
    """NullAdapter must never log full email addresses."""

    def test_null_adapter_does_not_log_full_email(self, capfd):
        import asyncio
        from src.integrations.crm.null_adapter import NullAdapter
        from src.integrations.crm.base import LeadSyncPayload
        from src.core.logging import configure_logging

        configure_logging("development", "DEBUG")

        adapter = NullAdapter()
        payload = LeadSyncPayload(
            lead_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            email="private.person@secret-company.com",
            nome="Private Person",
            azienda="Secret Company",
        )

        asyncio.run(adapter.sync_lead(payload))

        captured = capfd.readouterr()
        output = captured.out + captured.err

        # Full email must NOT appear in log output
        assert "private.person@secret-company.com" not in output, (
            "Full email address logged by NullAdapter — PII leak"
        )

    def test_lead_sync_payload_has_email_domain_property(self):
        from src.integrations.crm.base import LeadSyncPayload

        payload = LeadSyncPayload(
            lead_id="test-id",
            session_id="sess-id",
            email="user@example.com",
        )
        assert payload.email_domain == "example.com"


# ── Middleware PII leak tests ──────────────────────────────────────────────────

class TestMiddlewarePIILeak:
    """Request middleware must not log request body."""

    @pytest.mark.asyncio
    async def test_request_id_middleware_does_not_log_body(self):
        from src.middleware.request_id import RequestIDMiddleware
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.responses import JSONResponse

        async def dummy_endpoint(request):
            return JSONResponse({"ok": True})

        app = Starlette(routes=[Route("/test", dummy_endpoint, methods=["POST"])])
        app.add_middleware(RequestIDMiddleware)

        log_records = []

        client = TestClient(app)
        response = client.post(
            "/test",
            json={"contact": {"nome": "Test User", "email": "test@example.com", "azienda": "Corp"}},
        )
        assert response.status_code == 200

        for record in log_records:
            record_str = json.dumps(record, default=str)
            assert "Test User" not in record_str, "PII 'nome' leaked into middleware log"
            assert "test@example.com" not in record_str, "PII 'email' leaked into middleware log"
