"""Calendly integration schemas.

Data structures for booking link generation and booking metadata storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BookingLinkRequest:
    """Parameters for generating a pre-filled Calendly booking link.

    Calendly supports pre-filling guest information via URL query parameters.
    This reduces friction for leads who have already identified themselves.
    """

    lead_id: str
    """UUID of the lead to associate with the booking."""

    session_id: str
    """UUID of the session (for analytics correlation)."""

    # Optional pre-fill fields (passed as Calendly URL parameters)
    name: str | None = None
    """Lead's full name — pre-fills Calendly's 'name' field."""

    email: str | None = None
    """Lead's email — pre-fills Calendly's 'email' field."""

    # UTM tracking
    utm_source: str = "deepsearch_chatbot"
    utm_medium: str = "chatbot"
    utm_campaign: str = "demo_request"

    # Custom answers (Calendly question answers)
    custom_answers: dict[str, str] = field(default_factory=dict)


@dataclass
class BookingLinkResponse:
    """Result of a booking link generation request."""

    booking_url: str
    """Full Calendly URL with pre-filled parameters."""

    event_url: str
    """Base Calendly event type URL (without parameters)."""

    lead_id: str
    """UUID of the associated lead."""

    tracking_params: dict[str, str] = field(default_factory=dict)
    """All UTM and tracking parameters appended to the URL."""


@dataclass
class BookingMetadata:
    """Metadata stored after a booking is confirmed.

    This is populated via Calendly webhooks (future) or manual admin input.
    """

    lead_id: str
    session_id: str
    event_uri: str | None = None
    """Calendly event URI (from webhook payload)."""

    invitee_uri: str | None = None
    """Calendly invitee URI (identifies the specific booking)."""

    scheduled_at: str | None = None
    """ISO 8601 timestamp of the scheduled meeting."""

    status: str = "pending"
    """Booking status: pending | scheduled | cancelled | rescheduled"""
