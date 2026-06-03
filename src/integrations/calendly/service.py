"""Calendly booking link service.

Generates pre-filled Calendly booking links for qualified leads.

Architecture:
  - Stateless: generates booking URLs without requiring a Calendly API call
    (Calendly supports pre-filling via standard URL query parameters)
  - When CALENDLY_API_KEY is set: can verify the event type and pull metadata
  - When CALENDLY_API_KEY is absent: generates links using CALENDLY_EVENT_URL
    with UTM + pre-fill parameters only (no API verification)

SECURITY:
  - Lead PII (name, email) is passed as URL parameters ONLY when explicitly
    requested (some deployments may prefer not to pre-fill for privacy reasons)
  - Lead ID and session ID are always appended for analytics correlation
  - API key is NEVER appended to frontend-visible URLs
"""
from __future__ import annotations

from urllib.parse import urlencode, urlparse, urlunparse

import httpx

from src.core.config import get_settings
from src.core.logging import get_logger
from src.integrations.calendly.schemas import (
    BookingLinkRequest,
    BookingLinkResponse,
)

logger = get_logger(__name__)

_CALENDLY_API_BASE = "https://api.calendly.com"


def generate_booking_link(req: BookingLinkRequest) -> BookingLinkResponse:
    """Generate a Calendly booking link for a qualified lead.

    This is a synchronous, stateless operation. It builds a URL with
    pre-fill parameters — no API call is needed unless you want to verify
    the event type exists.

    Args:
        req: Booking link request with lead context.

    Returns:
        BookingLinkResponse with the full pre-filled URL.

    Raises:
        ValueError: If CALENDLY_EVENT_URL is not configured.
    """
    settings = get_settings()

    if not settings.calendly_event_url:
        raise ValueError(
            "CALENDLY_EVENT_URL is not configured. "
            "Set it in .env to enable booking link generation."
        )

    event_url = settings.calendly_event_url.rstrip("/")

    # Build tracking parameters
    params: dict[str, str] = {
        # UTM tracking
        "utm_source": req.utm_source,
        "utm_medium": req.utm_medium,
        "utm_campaign": req.utm_campaign,
        # DeepSearch correlation IDs (stored in Calendly's UTM fields)
        "utm_content": req.lead_id,
        "utm_term": req.session_id,
    }

    # Pre-fill lead information (reduces friction)
    if req.name:
        params["name"] = req.name
    if req.email:
        params["email"] = req.email

    # Custom question answers
    for key, value in req.custom_answers.items():
        params[f"a1"] = value  # Calendly uses a1, a2, ... for custom answers

    booking_url = f"{event_url}?{urlencode(params)}"

    logger.info(
        "calendly_booking_link_generated",
        lead_id=req.lead_id,
        session_id=req.session_id,
        event_url=event_url,
        # NOTE: never log name/email — PII
    )

    return BookingLinkResponse(
        booking_url=booking_url,
        event_url=event_url,
        lead_id=req.lead_id,
        tracking_params=params,
    )


async def get_event_type_info(event_type_uri: str) -> dict | None:
    """Fetch Calendly event type details via the REST API.

    Requires CALENDLY_API_KEY to be set.
    Returns None if the API key is missing or the request fails.

    Args:
        event_type_uri: Calendly event type URI
                        (e.g. https://api.calendly.com/event_types/XXXXX)
    """
    settings = get_settings()

    if not settings.calendly_api_key:
        logger.debug("calendly_api_key_not_set_skipping_event_type_fetch")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                event_type_uri,
                headers={
                    "Authorization": f"Bearer {settings.calendly_api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        logger.warning("calendly_api_request_failed", error=str(exc))
        return None


async def health_check() -> bool:
    """Verify Calendly API connectivity.

    Returns True if CALENDLY_API_KEY is set and the API responds successfully.
    Returns False if the key is absent or the API call fails.
    """
    settings = get_settings()

    if not settings.calendly_api_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{_CALENDLY_API_BASE}/users/me",
                headers={
                    "Authorization": f"Bearer {settings.calendly_api_key}",
                },
            )
            return response.status_code == 200
    except Exception:
        return False
