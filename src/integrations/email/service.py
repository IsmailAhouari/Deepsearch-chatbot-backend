"""Email service for transactional notifications via Resend.

Two outbound emails are triggered after Lead capture:
  - Operator Notification  → Commercial Team (every Request Type)
  - Lead Confirmation      → Lead (demo gets Booking Link; contact/generic get plain text)

Uses httpx directly against the Resend REST API.
No PII is written to log output.
"""
from __future__ import annotations

import time

import httpx

from src.core.config import Settings
from src.core.logging import get_logger
from src.integrations.calendly.schemas import BookingLinkRequest
from src.integrations.calendly.service import generate_booking_link

logger = get_logger(__name__)

_RESEND_EMAILS_URL = "https://api.resend.com/emails"
_MAX_ATTEMPTS = 3
_RETRY_DELAYS = (1, 2, 4)  # seconds to sleep after each failed attempt

_REQUEST_TYPE_LABELS: dict[str, str] = {
    "demo": "Demo Request",
    "contact": "Contact Request",
    "generic_request": "Generic Request",
}


class EmailService:
    """Simple transactional email service backed by Resend.

    Degrades gracefully when credentials are absent: methods return early
    with a warning log so the application runs without email in development.
    """

    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.resend_api_key
        self._from_address = settings.email_from_address
        self._notification_email = settings.inside_notification_email

    # ── Operator Notification ─────────────────────────────────────────────────

    def send_operator_notification(self, lead: object, request_type: str) -> None:
        """Send Operator Notification to the Commercial Team.

        Sends for every Request Type. Skips silently when RESEND_API_KEY or
        INSIDE_NOTIFICATION_EMAIL is absent.
        """
        if not self._api_key:
            logger.warning(
                "operator_notification_skipped",
                reason="RESEND_API_KEY not configured",
                lead_id=str(lead.id),
            )
            return
        if not self._notification_email:
            logger.warning(
                "operator_notification_skipped",
                reason="INSIDE_NOTIFICATION_EMAIL not configured",
                lead_id=str(lead.id),
            )
            return

        try:
            type_label = _REQUEST_TYPE_LABELS.get(request_type, request_type)
            subject = f"New Lead — {type_label}"
            body = _build_operator_body(lead, request_type, type_label)
            self._send(
                to=self._notification_email,
                subject=subject,
                text=body,
            )
            logger.info(
                "operator_notification_sent",
                lead_id=str(lead.id),
                request_type=request_type,
            )
        except Exception as exc:
            logger.error(
                "operator_notification_failed",
                lead_id=str(lead.id),
                attempts=_MAX_ATTEMPTS,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    # ── Lead Confirmation ─────────────────────────────────────────────────────

    def send_lead_confirmation(self, lead: object, request_type: str) -> None:
        """Send Lead Confirmation to the Lead after form submission.

        Demo Requests include a pre-filled Booking Link.
        When CALENDLY_EVENT_URL is absent, a plain placeholder message is sent instead.
        Contact and Generic Requests receive a plain confirmation (no Booking Link).
        """
        if not self._api_key:
            logger.warning(
                "lead_confirmation_skipped",
                reason="RESEND_API_KEY not configured",
                lead_id=str(lead.id),
            )
            return

        try:
            subject, body = self._build_confirmation(lead, request_type)
            self._send(to=lead.email, subject=subject, text=body)
            logger.info(
                "lead_confirmation_sent",
                lead_id=str(lead.id),
                request_type=request_type,
            )
        except Exception as exc:
            logger.error(
                "lead_confirmation_failed",
                lead_id=str(lead.id),
                attempts=_MAX_ATTEMPTS,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _build_confirmation(self, lead: object, request_type: str) -> tuple[str, str]:
        if request_type == "demo":
            booking_url = self._resolve_booking_url(lead)
            return (
                "La tua richiesta di demo è stata ricevuta — DeepSearch",
                _build_demo_confirmation_body(lead, booking_url),
            )
        # Issues 004 handles distinct contact/generic copy
        return (
            "La tua richiesta è stata ricevuta — DeepSearch",
            _build_plain_confirmation_body(lead),
        )

    def _resolve_booking_url(self, lead: object) -> str | None:
        """Return the Calendly Booking Link URL, or None if unconfigured."""
        try:
            req = BookingLinkRequest(
                lead_id=lead.id,
                session_id=lead.session_id,
                name=lead.nome,
                email=lead.email,
            )
            return generate_booking_link(req).booking_url
        except ValueError:
            logger.warning(
                "lead_confirmation_booking_link_unavailable",
                reason="CALENDLY_EVENT_URL not configured",
                lead_id=str(lead.id),
            )
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _send(self, *, to: str, subject: str, text: str) -> None:
        """POST to Resend with up to _MAX_ATTEMPTS tries and exponential backoff.

        Sleeps _RETRY_DELAYS[i] seconds BETWEEN attempts only — no sleep follows
        the final failed attempt before the exception is raised.
        """
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    _RESEND_EMAILS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "from": self._from_address,
                        "to": [to],
                        "subject": subject,
                        "text": text,
                    },
                )
                response.raise_for_status()
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_RETRY_DELAYS[attempt - 1])
        raise last_exc  # type: ignore[misc]


def _build_demo_confirmation_body(lead: object, booking_url: str | None) -> str:
    """Plain-text Lead Confirmation for a Demo Request."""
    lines = [
        f"Ciao {lead.nome or ''},",
        "",
        "Grazie per aver richiesto una demo di DeepSearch.",
        "La tua richiesta è stata ricevuta. Un referente ti contatterà entro 24 ore lavorative.",
        "",
    ]
    if booking_url:
        lines += [
            "Puoi prenotare direttamente un momento nel calendario del nostro team:",
            booking_url,
            "",
        ]
    else:
        lines += [
            "Il nostro team ti contatterà a breve per concordare un appuntamento.",
            "",
        ]
    lines += [
        "— Il team DeepSearch",
    ]
    return "\n".join(lines)


def _build_plain_confirmation_body(lead: object) -> str:
    """Plain-text Lead Confirmation for Contact and Generic Requests."""
    lines = [
        f"Ciao {lead.nome or ''},",
        "",
        "Grazie per averci contattato.",
        "La tua richiesta è stata ricevuta. Un referente ti risponderà entro 24 ore lavorative.",
        "",
        "— Il team DeepSearch",
    ]
    return "\n".join(lines)


def _build_operator_body(lead: object, request_type: str, type_label: str) -> str:
    """Build plain-text Operator Notification body with curated Lead data."""
    lines = [
        f"New {type_label} received via DeepSearch chatbot widget.",
        "",
        "── Contact ──────────────────────────────────",
        f"Name:     {lead.nome or '—'}",
        f"Company:  {lead.azienda or '—'}",
        f"Email:    {lead.email or '—'}",
        f"Phone:    {lead.telefono or '—'}",
        f"Role:     {lead.ruolo or '—'}",
        f"Country:  {lead.paese or '—'}",
        "",
        "── Qualification ────────────────────────────",
        f"Request Type: {type_label}",
        f"Target:       {lead.target or '—'}",
        f"Obiettivo:    {lead.obiettivo or '—'}",
        f"Geografia:    {lead.geografia or '—'}",
        f"Role:         {lead.role or '—'}",
    ]

    if lead.note:
        lines += ["", "── Notes ────────────────────────────────────", lead.note]

    extra = getattr(lead, "extra_qualification", {}) or {}
    if extra.get("source_flow"):
        lines += ["", f"Source flow:  {extra['source_flow']}"]

    lines += [
        "",
        "── Reference ────────────────────────────────",
        f"Lead ID: {lead.id}",
    ]

    return "\n".join(lines)
