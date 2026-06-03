"""Background CRM sync task.

Called as a FastAPI BackgroundTask after successful lead capture.
Runs OUTSIDE the database transaction — a CRM failure never affects
the lead capture response.

Simple fire-and-forget: one attempt, log the result.
"""
from __future__ import annotations

import uuid

from src.core.database import get_session_factory
from src.core.logging import get_logger
from src.integrations.crm.base import LeadSyncPayload
from src.integrations.crm.factory import get_crm_adapter
from src.models.lead import Lead

logger = get_logger(__name__)


async def sync_lead_to_crm(lead_id: uuid.UUID) -> None:
    """Sync a single lead to the CRM adapter.

    This function is safe to call from FastAPI BackgroundTasks.
    It creates its own database session independent of the request session.

    SECURITY: No PII is written to log output. Only lead_id and email domain.
    """
    adapter = get_crm_adapter()
    factory = get_session_factory()

    async with factory() as db:
        try:
            lead = await db.get(Lead, lead_id)
            if lead is None:
                logger.warning("crm_sync_lead_not_found", lead_id=str(lead_id))
                return

            payload = LeadSyncPayload(
                lead_id=str(lead.id),
                session_id=str(lead.session_id),
                nome=lead.nome,
                azienda=lead.azienda,
                email=lead.email,
                telefono=lead.telefono,
                target=lead.target,
                obiettivo=lead.obiettivo,
                geografia=lead.geografia,
                role=lead.role,
                locale=lead.locale or "it",
                extra_qualification=lead.extra_qualification or {},
            )

            result = await adapter.sync_lead(payload)

            if result.success:
                logger.info(
                    "crm_sync_success",
                    lead_id=str(lead_id),
                    email_domain=payload.email_domain,
                )
            else:
                logger.warning(
                    "crm_sync_failed",
                    lead_id=str(lead_id),
                    error=result.error_message,
                )

        except Exception as exc:
            logger.error(
                "crm_sync_unexpected_error",
                lead_id=str(lead_id),
                error_type=type(exc).__name__,
                error=str(exc),
            )
