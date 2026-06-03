"""CRM adapter base — Protocol definition and shared data classes.

All CRM adapters must implement the CRMAdapter Protocol:
  - async sync_lead(payload: LeadSyncPayload) → SyncResult
  - async health_check() → bool

The NullAdapter (default) satisfies this protocol.
Future adapters (HubSpot, Salesforce, Pipedrive) must also satisfy it.

SECURITY: LeadSyncPayload includes PII fields (nome, azienda, email).
Adapters MUST NOT log full PII in their implementation.
Log at most the email domain and lead_id for traceability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
import uuid


@dataclass
class LeadSyncPayload:
    """Data payload sent to the CRM adapter for each lead.

    PII fields are included for CRMs that require full contact data.
    Non-PII adapters should strip PII before transmitting.
    """

    # Identifiers
    lead_id: str
    session_id: str

    # Contact PII — MUST NOT be logged by adapters
    nome: str = ""
    azienda: str = ""
    email: str = ""
    telefono: str | None = None
    ruolo: str | None = None
    paese: str | None = None

    # Canonical qualification
    target: str | None = None
    obiettivo: str | None = None
    geografia: str | None = None
    role: str | None = None

    # Session metadata (non-PII)
    locale: str = "it"
    source_flow: str | None = None
    created_at: str = ""

    # Overflow
    extra_qualification: dict[str, Any] = field(default_factory=dict)

    @property
    def email_domain(self) -> str:
        """Safe non-PII identifier for logging."""
        if "@" in self.email:
            return self.email.split("@", 1)[1]
        return "unknown"


@dataclass
class SyncResult:
    """Result returned by a CRM adapter sync_lead call."""

    success: bool
    crm_lead_id: str | None = None
    error_message: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CRMAdapter(Protocol):
    """Protocol that all CRM adapters must implement.

    Usage::

        adapter: CRMAdapter = NullAdapter()
        result = await adapter.sync_lead(payload)
        is_healthy = await adapter.health_check()
    """

    async def sync_lead(self, lead: LeadSyncPayload) -> SyncResult:
        """Push a lead to the CRM system.

        Must be idempotent — the same lead_id submitted twice should not
        create a duplicate CRM record (use upsert semantics where possible).

        MUST NOT raise — return SyncResult(success=False, error_message=...)
        on any failure so the retry loop can handle it gracefully.
        """
        ...

    async def health_check(self) -> bool:
        """Return True if the CRM system is reachable."""
        ...
