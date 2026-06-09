"""Background tasks for post-capture side effects.

All tasks are called as FastAPI BackgroundTasks after successful lead capture.
They run OUTSIDE the database transaction — a task failure never affects
the lead capture response.
"""
from __future__ import annotations

import uuid

from src.core.config import get_settings
from src.core.database import get_session_factory
from src.core.logging import get_logger
from src.integrations.crm.base import LeadSyncPayload
from src.integrations.crm.factory import get_crm_adapter
from src.integrations.email.service import EmailService
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


async def send_notification_emails(lead_id: uuid.UUID, request_type: str) -> None:
    """Send Operator Notification (and later Lead Confirmation) after lead capture.

    Runs OUTSIDE the request transaction. Email failure never affects the
    lead capture response.

    SECURITY: No PII is written to log output.
    """
    factory = get_session_factory()

    async with factory() as db:
        try:
            lead = await db.get(Lead, lead_id)
            service = EmailService(get_settings())
        except Exception as exc:
            logger.error(
                "notification_unexpected_error",
                lead_id=str(lead_id),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return

        if lead is None:
            logger.warning("notification_lead_not_found", lead_id=str(lead_id))
            return

        # Send each email independently — a failure in one must not skip the other.
        # The service methods contain their own faults, but we isolate here as
        # defence in depth so the two emails are never coupled.
        for send in (
            lambda: service.send_operator_notification(lead, request_type),
            lambda: service.send_lead_confirmation(lead, request_type),
        ):
            try:
                send()
            except Exception as exc:
                logger.error(
                    "notification_unexpected_error",
                    lead_id=str(lead_id),
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
