"""Booking link service (Cal.com).

Generates pre-filled Cal.com booking links for qualified Leads.

Architecture:
  - Stateless: builds booking URLs by appending query parameters to
    BOOKING_EVENT_URL. No provider API call is required — Cal.com pre-fills its
    booking form from standard URL query parameters (``name``, ``email``).

SECURITY:
  - Lead PII (name, email) is passed as URL parameters only when present.
  - Lead ID and Session ID are appended for analytics correlation (UTM fields).
  - No API key is appended to frontend-visible URLs.
"""
from __future__ import annotations

from urllib.parse import urlencode

from src.core.config import get_settings
from src.core.logging import get_logger
from src.integrations.booking.schemas import (
    BookingLinkRequest,
    BookingLinkResponse,
)

logger = get_logger(__name__)


def generate_booking_link(req: BookingLinkRequest) -> BookingLinkResponse:
    """Generate a Cal.com booking link for a qualified Lead.

    Synchronous and stateless: builds a URL with pre-fill parameters — no
    provider API call is made.

    Args:
        req: Booking link request with Lead context.

    Returns:
        BookingLinkResponse with the full pre-filled URL.

    Raises:
        ValueError: If BOOKING_EVENT_URL is not configured.
    """
    settings = get_settings()

    if not settings.booking_event_url:
        raise ValueError(
            "BOOKING_EVENT_URL is not configured. "
            "Set it in .env to enable booking link generation."
        )

    event_url = settings.booking_event_url.rstrip("/")

    params: dict[str, str] = {
        # UTM tracking (Cal.com captures these for the host on the booking page)
        "utm_source": req.utm_source,
        "utm_medium": req.utm_medium,
        "utm_campaign": req.utm_campaign,
        # DeepSearch correlation IDs (stored in the provider's UTM fields)
        "utm_content": req.lead_id,
        "utm_term": req.session_id,
    }

    # Pre-fill Lead information (reduces friction). Cal.com uses the same
    # ``name`` / ``email`` query-parameter names as Calendly.
    if req.name:
        params["name"] = req.name
    if req.email:
        params["email"] = req.email

    booking_url = f"{event_url}?{urlencode(params)}"

    logger.info(
        "booking_link_generated",
        lead_id=str(req.lead_id),
        session_id=str(req.session_id),
        event_url=event_url,
        # NOTE: never log name/email — PII
    )

    return BookingLinkResponse(
        booking_url=booking_url,
        event_url=event_url,
        lead_id=req.lead_id,
        tracking_params=params,
    )
