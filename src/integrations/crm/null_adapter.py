"""NullAdapter — default CRM adapter for development and testing.

The NullAdapter accepts all sync requests and returns a successful result
without actually sending any data to an external CRM system.

This is the default CRM_ADAPTER_CLASS. Replace with a real adapter when
a CRM target is confirmed.

CRM Adapter Protocol::

    class CRMAdapter(Protocol):
        async def sync_lead(self, lead: LeadSyncPayload) -> SyncResult: ...
        async def health_check() → bool: ...
"""
from __future__ import annotations

from src.core.logging import get_logger
from src.integrations.crm.base import LeadSyncPayload, SyncResult

logger = get_logger(__name__)


class NullAdapter:
    """No-op CRM adapter — logs and acknowledges without transmitting data.

    Useful for:
    - Local development
    - Staging environments with no CRM configured
    - Testing

    SECURITY: Only lead_id and email_domain are logged — never full email or name.
    """

    async def sync_lead(self, lead: LeadSyncPayload) -> SyncResult:
        """Acknowledge the sync request without sending data anywhere."""
        logger.info(
            "crm_sync_null",
            lead_id=lead.lead_id,
            # email_domain is safe to log — it's not PII
            email_domain=lead.email_domain if lead.email else "unknown",
            adapter="NullAdapter",
            message="CRM sync acknowledged but not transmitted (NullAdapter).",
        )
        return SyncResult(
            success=True,
            crm_lead_id=None,
            raw_response={"adapter": "NullAdapter", "action": "no-op"},
        )

    async def health_check(self) -> bool:
        """Always healthy — no external dependency."""
        return True
