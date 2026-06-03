"""CRM integration tests.

Tests verify:
  - NullAdapter returns success and does NOT raise
  - NullAdapter health_check returns True
  - CRM factory loads NullAdapter by default
  - CRM factory handles invalid adapter class gracefully
  - LeadSyncPayload email_domain property works correctly
  - sync_lead_to_crm task handles missing lead gracefully
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── NullAdapter unit tests ─────────────────────────────────────────────────────

class TestNullAdapter:
    """NullAdapter must accept any lead and always succeed."""

    def test_null_adapter_sync_lead_succeeds(self):
        from src.integrations.crm.null_adapter import NullAdapter
        from src.integrations.crm.base import LeadSyncPayload

        adapter = NullAdapter()
        payload = LeadSyncPayload(
            lead_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            email="contact@example.com",
            target="azienda",
            obiettivo="due_diligence",
            geografia="Europa",
            role="legal",
        )

        import asyncio
        result = asyncio.run(adapter.sync_lead(payload))

        assert result.success is True

    def test_null_adapter_health_check_returns_true(self):
        from src.integrations.crm.null_adapter import NullAdapter

        adapter = NullAdapter()
        import asyncio
        result = asyncio.run(adapter.health_check())
        assert result is True

    def test_null_adapter_implements_crm_protocol(self):
        from src.integrations.crm.base import CRMAdapter
        from src.integrations.crm.null_adapter import NullAdapter

        adapter = NullAdapter()
        assert isinstance(adapter, CRMAdapter)

    def test_lead_sync_payload_email_domain_property(self):
        from src.integrations.crm.base import LeadSyncPayload

        payload = LeadSyncPayload(
            lead_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            email="user@corporate.example.com",
        )
        assert payload.email_domain == "corporate.example.com"

    def test_email_domain_unknown_when_no_email(self):
        from src.integrations.crm.base import LeadSyncPayload

        payload = LeadSyncPayload(
            lead_id=str(uuid.uuid4()),
            session_id=str(uuid.uuid4()),
            email="",
        )
        assert payload.email_domain == "unknown"


class TestCRMFactory:
    """CRM factory loads adapters by dotted path."""

    def setup_method(self):
        import src.integrations.crm.factory as factory_module
        factory_module._cached_adapter = None

    def test_factory_loads_null_adapter_by_default(self):
        from src.integrations.crm.factory import get_crm_adapter
        from src.integrations.crm.null_adapter import NullAdapter
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "CRM_ADAPTER_CLASS": "src.integrations.crm.null_adapter.NullAdapter",
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()

            import src.integrations.crm.factory as factory_module
            factory_module._cached_adapter = None

            adapter = get_crm_adapter()
            assert isinstance(adapter, NullAdapter)

    def test_factory_falls_back_on_invalid_class(self):
        from src.integrations.crm.factory import get_crm_adapter
        from src.integrations.crm.null_adapter import NullAdapter
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "CRM_ADAPTER_CLASS": "src.integrations.crm.nonexistent.NonExistentAdapter",
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()

            import src.integrations.crm.factory as factory_module
            factory_module._cached_adapter = None

            adapter = get_crm_adapter()
            assert isinstance(adapter, NullAdapter)

    def teardown_method(self):
        import src.integrations.crm.factory as factory_module
        factory_module._cached_adapter = None
        from src.core.config import get_settings
        get_settings.cache_clear()


# ── sync_lead_to_crm task tests ────────────────────────────────────────────────

class TestSyncLeadTask:
    """Test the simplified fire-and-forget CRM sync task."""

    @pytest.mark.asyncio
    async def test_sync_task_skips_missing_lead(self):
        """If the lead is not found in DB, the task exits cleanly without error."""
        from src.integrations.tasks import sync_lead_to_crm

        lead_id = uuid.uuid4()

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("src.integrations.tasks.get_session_factory", return_value=mock_factory):
            # Should NOT raise even if lead is missing
            await sync_lead_to_crm(lead_id)

    @pytest.mark.asyncio
    async def test_sync_task_calls_adapter_on_success(self):
        """On adapter success, logs crm_sync_success."""
        from src.integrations.tasks import sync_lead_to_crm
        from src.integrations.crm.base import SyncResult

        lead_id = uuid.uuid4()
        mock_lead = MagicMock()
        mock_lead.id = lead_id
        mock_lead.session_id = uuid.uuid4()
        mock_lead.email = "test@example.com"
        mock_lead.nome = "Test User"
        mock_lead.azienda = "TestCo"
        mock_lead.telefono = None
        mock_lead.target = "azienda"
        mock_lead.obiettivo = "due_diligence"
        mock_lead.geografia = "Europa"
        mock_lead.role = "legal"
        mock_lead.locale = "it"
        mock_lead.extra_qualification = {}

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_lead)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        mock_adapter = AsyncMock()
        mock_adapter.sync_lead = AsyncMock(
            return_value=SyncResult(success=True, crm_lead_id="CRM-001")
        )

        with patch("src.integrations.tasks.get_session_factory", return_value=mock_factory):
            with patch("src.integrations.tasks.get_crm_adapter", return_value=mock_adapter):
                await sync_lead_to_crm(lead_id)

        mock_adapter.sync_lead.assert_called_once()
