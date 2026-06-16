"""Booking integration schemas.

Provider-neutral data structures for scheduling-link generation. The active
provider is Cal.com (Cloud, free tier); the same URL-prefill approach works for
any provider that pre-fills its booking form via query parameters.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BookingLinkRequest:
    """Parameters for generating a pre-filled booking link.

    Cal.com pre-fills guest information via URL query parameters (``name``,
    ``email``), reducing friction for Leads who have already identified
    themselves during qualification.
    """

    lead_id: str
    """UUID of the Lead to associate with the booking."""

    session_id: str
    """UUID of the Session (for analytics correlation)."""

    # Optional pre-fill fields (passed as booking-form URL parameters)
    name: str | None = None
    """Lead's full name — pre-fills the booking form's 'name' field."""

    email: str | None = None
    """Lead's email — pre-fills the booking form's 'email' field."""

    # UTM tracking. Cal.com captures these and surfaces them to the host on the
    # booking details page. NOTE: Cal.com does not reliably round-trip UTM values
    # into webhooks — when booking->Lead correlation is built, use a hidden
    # booking question carrying ``lead_id`` instead of utm_content.
    utm_source: str = "deepsearch_chatbot"
    utm_medium: str = "chatbot"
    utm_campaign: str = "demo_request"


@dataclass
class BookingLinkResponse:
    """Result of a booking-link generation request."""

    booking_url: str
    """Full booking URL with pre-filled parameters."""

    event_url: str
    """Base event URL (without parameters)."""

    lead_id: str
    """UUID of the associated Lead."""

    tracking_params: dict[str, str] = field(default_factory=dict)
    """All UTM and tracking parameters appended to the URL."""


@dataclass
class BookingMetadata:
    """Metadata stored after a booking is confirmed.

    Placeholder for the future booking-confirmation path. When implemented,
    correlation back to a Lead should use a **hidden booking question** carrying
    ``lead_id`` (Cal.com webhooks expose hidden-question answers; they do not
    reliably expose UTM parameters).
    """

    lead_id: str
    session_id: str
    event_uri: str | None = None
    """Provider event URI (from webhook payload)."""

    invitee_uri: str | None = None
    """Provider invitee URI (identifies the specific booking)."""

    scheduled_at: str | None = None
    """ISO 8601 timestamp of the scheduled meeting."""

    status: str = "pending"
    """Booking status: pending | scheduled | cancelled | rescheduled"""
