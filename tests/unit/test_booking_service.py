"""Unit tests for the Cal.com booking link service.

Tests verify:
  - generate_booking_link produces correct URL structure
  - UTM parameters are correctly appended
  - Lead ID and session ID are embedded as tracking params
  - Pre-fill fields (name, email) are conditionally included
  - ValueError raised when BOOKING_EVENT_URL is not configured
  - PII is NOT logged
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

from src.integrations.booking.schemas import BookingLinkRequest

_EVENT_URL = "https://cal.com/deepsearch/demo"


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Clear settings cache before and after each test."""
    from src.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_request(**kwargs) -> BookingLinkRequest:
    """Create a test BookingLinkRequest."""
    defaults = {
        "lead_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
    }
    defaults.update(kwargs)
    return BookingLinkRequest(**defaults)


class TestBookingLinkGeneration:
    """Test URL generation for Cal.com booking links."""

    def test_generates_url_with_utm_params(self):
        """Booking link includes utm_source, utm_medium, utm_campaign."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()

            req = _make_request()
            result = generate_booking_link(req)

        assert "utm_source=deepsearch_chatbot" in result.booking_url
        assert "utm_medium=chatbot" in result.booking_url
        assert "utm_campaign=demo_request" in result.booking_url

    def test_lead_id_embedded_in_url(self):
        """Lead ID is embedded as utm_content for correlation."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        lead_id = str(uuid.uuid4())

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request(lead_id=lead_id)
            result = generate_booking_link(req)

        assert lead_id in result.booking_url
        assert result.lead_id == lead_id

    def test_session_id_embedded_in_url(self):
        """Session ID is embedded as utm_term for analytics correlation."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        session_id = str(uuid.uuid4())

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request(session_id=session_id)
            result = generate_booking_link(req)

        assert session_id in result.booking_url

    def test_name_prefill_included_when_provided(self):
        """When name is provided, it appears as a 'name' param in the URL."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request(name="Mario Rossi")
            result = generate_booking_link(req)

        assert "name=" in result.booking_url
        assert "Mario" in result.booking_url

    def test_name_not_in_url_when_not_provided(self):
        """When name is not provided, 'name=' must not appear in the URL."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request()  # no name
            result = generate_booking_link(req)

        assert "name=" not in result.booking_url

    def test_event_url_base_is_preserved(self):
        """The base Cal.com event URL appears at the start of the booking link."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        event_url = "https://cal.com/deepsearch/enterprise-demo"

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": event_url,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request()
            result = generate_booking_link(req)

        assert result.booking_url.startswith(event_url)
        assert result.event_url == event_url

    def test_raises_when_event_url_not_configured(self):
        """ValueError raised when BOOKING_EVENT_URL is not in environment."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        env_without_booking = {
            k: v for k, v in os.environ.items()
            if k != "BOOKING_EVENT_URL"
        }
        env_without_booking.update({
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        })
        env_without_booking.pop("BOOKING_EVENT_URL", None)

        with patch.dict(os.environ, env_without_booking, clear=True):
            get_settings.cache_clear()

            req = _make_request()
            with pytest.raises(ValueError, match="BOOKING_EVENT_URL"):
                generate_booking_link(req)

    def test_booking_url_is_a_valid_url_string(self):
        """Booking URL must be a valid URL starting with https://."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request()
            result = generate_booking_link(req)

        assert result.booking_url.startswith("https://")
        assert "?" in result.booking_url  # must have query string

    def test_tracking_params_dict_is_populated(self):
        """tracking_params dict in response contains all appended parameters."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request()
            result = generate_booking_link(req)

        assert "utm_source" in result.tracking_params
        assert "utm_content" in result.tracking_params  # lead_id
        assert "utm_term" in result.tracking_params  # session_id


class TestBookingLinkPIISafety:
    """Booking link generation must not log raw PII."""

    def test_email_not_logged_by_service(self, capfd):
        """generate_booking_link must not write raw email to stdout/stderr."""
        from src.integrations.booking.service import generate_booking_link
        from src.core.config import get_settings
        from src.core.logging import configure_logging

        configure_logging("development", "DEBUG")

        with patch.dict(os.environ, {
            "BOOKING_EVENT_URL": _EVENT_URL,
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            req = _make_request(name="Mario Rossi", email="private@email.com")
            generate_booking_link(req)

        captured = capfd.readouterr()
        output = captured.out + captured.err

        assert "private@email.com" not in output, (
            "Raw email address was logged by the booking service — this leaks PII"
        )
