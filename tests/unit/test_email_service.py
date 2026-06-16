"""Unit tests for EmailService.send_operator_notification().

Tests verify external behaviour through the public interface only:
- Resend API is called with the correct recipient and content
- Service degrades gracefully when credentials are absent
- PII is never written to log output

Run: pytest tests/unit/test_email_service.py -v
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_lead(**overrides) -> MagicMock:
    """Return a mock Lead with sensible defaults for notification tests."""
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.session_id = uuid.uuid4()
    lead.nome = "Mario Rossi"
    lead.azienda = "Acme SpA"
    lead.email = "mario.rossi@acme.it"
    lead.telefono = "+39 02 1234567"
    lead.ruolo = "Compliance Officer"
    lead.paese = "Italia"
    lead.note = "Interested in AML screening."
    lead.target = "azienda"
    lead.obiettivo = "aml"
    lead.geografia = "Europa"
    lead.role = "compliance"
    lead.extra_qualification = {"source_flow": "flowB_aml"}
    for k, v in overrides.items():
        setattr(lead, k, v)
    return lead


def _make_service(*, api_key: str = "re_test_key", notification_email: str = "inside@deepsearch.ch"):
    """Instantiate EmailService with test credentials."""
    from src.integrations.email.service import EmailService
    from src.core.config import get_settings

    with patch.dict(os.environ, {
        "RESEND_API_KEY": api_key,
        "INSIDE_NOTIFICATION_EMAIL": notification_email,
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    }):
        get_settings.cache_clear()
        return EmailService(get_settings())


# ── Operator Notification ─────────────────────────────────────────────────────

class TestOperatorNotification:

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def test_notification_sends_to_configured_recipient(self):
        """Operator Notification is addressed to INSIDE_NOTIFICATION_EMAIL."""
        service = _make_service(notification_email="team@deepsearch.ch")
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.raise_for_status.return_value = None
            mock_httpx.post.return_value = mock_response

            service.send_operator_notification(lead, "demo")

        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args.kwargs
        payload = call_kwargs["json"]
        assert "team@deepsearch.ch" in payload["to"]

    def test_notification_skips_when_api_key_absent(self, capfd):
        """No HTTP call is made when RESEND_API_KEY is not configured."""
        from src.integrations.email.service import EmailService
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "INSIDE_NOTIFICATION_EMAIL": "inside@deepsearch.ch",
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            # Remove RESEND_API_KEY if set
            os.environ.pop("RESEND_API_KEY", None)
            get_settings.cache_clear()
            service = EmailService(get_settings())

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            service.send_operator_notification(_make_lead(), "demo")

        mock_httpx.post.assert_not_called()

    def test_notification_skips_when_recipient_absent(self):
        """No HTTP call is made when INSIDE_NOTIFICATION_EMAIL is not configured."""
        from src.integrations.email.service import EmailService
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "RESEND_API_KEY": "re_test_key",
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            os.environ.pop("INSIDE_NOTIFICATION_EMAIL", None)
            get_settings.cache_clear()
            service = EmailService(get_settings())

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            service.send_operator_notification(_make_lead(), "demo")

        mock_httpx.post.assert_not_called()

    def test_subject_contains_request_type(self):
        """Subject line includes the human-readable Request Type label."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        assert "demo" in payload["subject"].lower() or "Demo" in payload["subject"]

    def test_body_contains_lead_name_and_company(self):
        """Email body includes the Lead's nome and azienda."""
        service = _make_service()
        lead = _make_lead(nome="Giulia Bianchi", azienda="TechCorp Srl")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "contact")

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert "Giulia Bianchi" in body
        assert "TechCorp Srl" in body

    def test_body_contains_lead_email(self):
        """Email body includes the Lead's email address."""
        service = _make_service()
        lead = _make_lead(email="giulia@techcorp.it")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert "giulia@techcorp.it" in body

    def test_body_contains_qualification_fields(self):
        """Email body includes obiettivo, target, and geografia."""
        service = _make_service()
        lead = _make_lead(obiettivo="due_diligence", target="persona", geografia="USA")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert "due_diligence" in body
        assert "persona" in body
        assert "USA" in body

    def test_body_contains_lead_id(self):
        """Email body includes the lead_id for CRM cross-reference."""
        service = _make_service()
        lead = _make_lead()
        lead_id_str = str(lead.id)

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert lead_id_str in body

    def test_notification_fires_for_all_request_types(self):
        """Operator Notification is sent for demo, contact, and generic_request."""
        for request_type in ("demo", "contact", "generic_request"):
            service = _make_service()
            lead = _make_lead()

            with patch("src.integrations.email.service.httpx") as mock_httpx:
                mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
                service.send_operator_notification(lead, request_type)

            mock_httpx.post.assert_called_once(), (
                f"Expected httpx.post for request_type='{request_type}'"
            )

    def test_lead_email_not_in_logs(self, capfd):
        """PII (Lead email) is never written to log output."""
        service = _make_service()
        lead = _make_lead(email="private.person@secret.company.com")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        captured = capfd.readouterr()
        output = captured.out + captured.err
        assert "private.person@secret.company.com" not in output

    def test_operator_notification_contains_body_build_failure(self):
        """A failure while building the operator body is contained, not propagated.

        Guards against a Lead model change that removes/renames an attribute the
        body builder reads — the exception must not escape and skip downstream work.
        """
        class _ExplodingLead:
            id = uuid.uuid4()
            session_id = uuid.uuid4()
            nome = "Mario"
            email = "mario@acme.it"

            @property
            def azienda(self):
                raise AttributeError("azienda removed by a model migration")

        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            # Must NOT raise — the body-build failure is contained and logged.
            service.send_operator_notification(_ExplodingLead(), "demo")

        # The failure happened before _send, so no HTTP call was attempted.
        mock_httpx.post.assert_not_called()


# ── Lead Confirmation ─────────────────────────────────────────────────────────

class TestLeadConfirmation:

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def _fake_booking_response(self, booking_url: str = "https://cal.com/deepsearch/demo?name=test"):
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.booking_url = booking_url
        return resp

    def test_confirmation_contains_body_build_failure(self):
        """A failure while building the confirmation body is contained, not propagated."""
        class _ExplodingLead:
            id = uuid.uuid4()
            session_id = uuid.uuid4()
            email = "mario@acme.it"

            @property
            def nome(self):
                raise AttributeError("nome removed by a model migration")

        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            # Must NOT raise — contained and logged.
            service.send_lead_confirmation(_ExplodingLead(), "contact")

        mock_httpx.post.assert_not_called()

    def test_confirmation_sends_to_lead_email_for_demo(self):
        """Lead Confirmation for a Demo Request is addressed to the Lead's email."""
        service = _make_service()
        lead = _make_lead(email="giulia@testco.it")

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=self._fake_booking_response()):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        mock_httpx.post.assert_called_once()
        payload = mock_httpx.post.call_args.kwargs["json"]
        assert "giulia@testco.it" in payload["to"]

    def test_confirmation_body_contains_booking_link_for_demo(self):
        """Lead Confirmation for a Demo Request includes the Booking Link URL."""
        service = _make_service()
        lead = _make_lead()
        booking_url = "https://cal.com/deepsearch/demo?lead_id=abc"

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=self._fake_booking_response(booking_url)):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert booking_url in body

    def test_confirmation_generates_booking_link_with_lead_name_and_email(self):
        """Booking Link is generated pre-filled with the Lead's nome and email."""
        service = _make_service()
        lead = _make_lead(nome="Carlo Verdi", email="carlo@verdi.it")

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=self._fake_booking_response()) as mock_gen:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        mock_gen.assert_called_once()
        req = mock_gen.call_args.args[0]
        assert req.name == "Carlo Verdi"
        assert req.email == "carlo@verdi.it"
        assert req.lead_id == lead.id
        assert req.session_id == lead.session_id

    def test_confirmation_uses_placeholder_when_booking_url_absent(self):
        """When BOOKING_EVENT_URL is missing, email is sent with placeholder text."""
        service = _make_service()
        lead = _make_lead()

        # generate_booking_link raises ValueError when BOOKING_EVENT_URL is unset
        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   side_effect=ValueError("BOOKING_EVENT_URL not configured")):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        # Email is still sent — degraded but not dropped
        mock_httpx.post.assert_called_once()
        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        # Placeholder text replaces the booking link
        assert "cal.com" not in body
        assert len(body) > 20  # non-empty confirmation

    def test_confirmation_skips_when_api_key_absent(self):
        """No HTTP call is made when RESEND_API_KEY is not configured."""
        from src.integrations.email.service import EmailService
        from src.core.config import get_settings

        with patch.dict(os.environ, {
            "INSIDE_NOTIFICATION_EMAIL": "inside@deepsearch.ch",
            "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
        }):
            get_settings.cache_clear()
            os.environ.pop("RESEND_API_KEY", None)
            get_settings.cache_clear()
            service = EmailService(get_settings())

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            service.send_lead_confirmation(_make_lead(), "demo")

        mock_httpx.post.assert_not_called()


# ── Lead Confirmation: Contact + Generic ─────────────────────────────────────

class TestLeadConfirmationContactGeneric:
    """Contact and Generic Request confirmations: email sent, no Booking Link."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    @pytest.mark.parametrize("request_type", ["contact", "generic_request"])
    def test_confirmation_sends_to_lead_email(self, request_type):
        """Lead Confirmation for contact/generic is addressed to the Lead's email."""
        service = _make_service()
        lead = _make_lead(email="contact@example.it")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, request_type)

        mock_httpx.post.assert_called_once()
        payload = mock_httpx.post.call_args.kwargs["json"]
        assert "contact@example.it" in payload["to"]

    @pytest.mark.parametrize("request_type", ["contact", "generic_request"])
    def test_confirmation_body_contains_no_booking_link(self, request_type):
        """Lead Confirmation for contact/generic does not include a Booking Link."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, request_type)

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert "cal.com" not in body

    @pytest.mark.parametrize("request_type", ["contact", "generic_request"])
    def test_booking_link_not_generated_for_non_demo(self, request_type):
        """generate_booking_link is never called for contact or generic requests."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link") as mock_gen:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, request_type)

        mock_gen.assert_not_called()

    @pytest.mark.parametrize("request_type", ["contact", "generic_request"])
    def test_confirmation_body_is_non_empty(self, request_type):
        """Lead Confirmation for contact/generic has a non-empty, meaningful body."""
        service = _make_service()
        lead = _make_lead(nome="Anna Ferrari")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, request_type)

        payload = mock_httpx.post.call_args.kwargs["json"]
        body = payload.get("text", "") + payload.get("html", "")
        assert "Anna Ferrari" in body
        assert len(body) > 50


# ── Retry behaviour ──────────────────────────────────────────────────────────

class TestRetryBehavior:
    """_send() retries up to 3 times with 1s→2s→4s exponential backoff."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def _fail_response(self):
        r = MagicMock()
        r.raise_for_status.side_effect = Exception("Resend 503")
        return r

    def _ok_response(self):
        r = MagicMock()
        r.raise_for_status.return_value = None
        return r

    def test_retries_on_transient_failure_then_succeeds(self):
        """Two failures then a success uses 3 total calls."""
        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time") as mock_time:
            mock_httpx.post.side_effect = [
                self._fail_response(),
                self._fail_response(),
                self._ok_response(),
            ]
            service._send(to="a@b.com", subject="S", text="T")

        assert mock_httpx.post.call_count == 3
        assert mock_time.sleep.call_count == 2

    def test_retry_delays_are_1s_then_2s(self):
        """Sleep delays between attempts are 1s then 2s."""
        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time") as mock_time:
            mock_httpx.post.side_effect = [
                self._fail_response(),
                self._fail_response(),
                self._ok_response(),
            ]
            service._send(to="a@b.com", subject="S", text="T")

        sleep_calls = [c.args[0] for c in mock_time.sleep.call_args_list]
        assert sleep_calls == [1, 2]

    def test_three_failures_exhausts_retries_and_raises(self):
        """After 3 failures _send() raises and has made exactly 3 HTTP calls."""
        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"):
            mock_httpx.post.return_value = self._fail_response()
            with pytest.raises(Exception, match="Resend 503"):
                service._send(to="a@b.com", subject="S", text="T")

        assert mock_httpx.post.call_count == 3

    def test_no_sleep_after_final_failed_attempt(self):
        """Sleeps occur only BETWEEN attempts (1s, 2s) — never after the last failure.

        On three failures the backoff is 1s then 2s, then the exception is raised
        immediately. The trailing 4s sleep would be pure wasted latency.
        """
        service = _make_service()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time") as mock_time:
            mock_httpx.post.return_value = self._fail_response()
            with pytest.raises(Exception):
                service._send(to="a@b.com", subject="S", text="T")

        sleep_calls = [c.args[0] for c in mock_time.sleep.call_args_list]
        assert sleep_calls == [1, 2]

    def test_operator_notification_swallows_exhausted_retries(self):
        """send_operator_notification logs ERROR but does not raise after all retries fail."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"):
            mock_httpx.post.return_value = self._fail_response()
            service.send_operator_notification(lead, "demo")  # must NOT raise

        assert mock_httpx.post.call_count == 3

    def test_lead_confirmation_swallows_exhausted_retries(self):
        """send_lead_confirmation logs ERROR but does not raise after all retries fail."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"), \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=MagicMock(booking_url="https://cal.com/t")):
            mock_httpx.post.return_value = self._fail_response()
            service.send_lead_confirmation(lead, "demo")  # must NOT raise

        assert mock_httpx.post.call_count == 3

    def test_operator_failure_does_not_prevent_lead_confirmation(self):
        """Independent sends: Operator Notification failure doesn't skip Lead Confirmation."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"), \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=MagicMock(booking_url="https://cal.com/t")):
            mock_httpx.post.side_effect = [
                # Operator Notification: 3 failures
                self._fail_response(), self._fail_response(), self._fail_response(),
                # Lead Confirmation: succeeds
                self._ok_response(),
            ]
            service.send_operator_notification(lead, "demo")
            service.send_lead_confirmation(lead, "demo")

        assert mock_httpx.post.call_count == 4

    def test_operator_failure_logs_error_detail(self):
        """The ERROR log for an exhausted Operator Notification carries the failure message."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"), \
             patch("src.integrations.email.service.logger") as mock_logger:
            mock_httpx.post.return_value = self._fail_response()
            service.send_operator_notification(lead, "demo")

        assert mock_logger.error.call_args_list, "expected an error log after exhausted retries"
        kwargs = mock_logger.error.call_args_list[-1].kwargs
        assert kwargs.get("error") == "Resend 503"

    def test_lead_confirmation_failure_logs_error_detail(self):
        """The ERROR log for an exhausted Lead Confirmation carries the failure message."""
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"), \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=MagicMock(booking_url="https://cal.com/t")), \
             patch("src.integrations.email.service.logger") as mock_logger:
            mock_httpx.post.return_value = self._fail_response()
            service.send_lead_confirmation(lead, "demo")

        assert mock_logger.error.call_args_list, "expected an error log after exhausted retries"
        kwargs = mock_logger.error.call_args_list[-1].kwargs
        assert kwargs.get("error") == "Resend 503"

    def test_logged_error_detail_contains_no_pii(self, capfd):
        """The logged error string never leaks Lead PII."""
        service = _make_service()
        lead = _make_lead(email="private.person@secret.company.com", nome="Segreto Nome")

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.time"):
            mock_httpx.post.return_value = self._fail_response()
            service.send_operator_notification(lead, "demo")

        output = "".join(capfd.readouterr())
        assert "private.person@secret.company.com" not in output
        assert "Segreto Nome" not in output


# ── Background task ───────────────────────────────────────────────────────────

class TestSendNotificationEmailsTask:
    """send_notification_emails background task handles missing leads and calls service."""

    @pytest.mark.asyncio
    async def test_task_skips_missing_lead(self):
        """Task exits cleanly without error when lead is not found."""
        from src.integrations.tasks import send_notification_emails

        lead_id = uuid.uuid4()
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=None)
        mock_session.__aenter__ = MagicMock(return_value=mock_session)
        mock_session.__aexit__ = MagicMock(return_value=False)

        # Make session.get behave as async
        from unittest.mock import AsyncMock
        mock_session.get = AsyncMock(return_value=None)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("src.integrations.tasks.get_session_factory", return_value=mock_factory):
            await send_notification_emails(lead_id, "demo")  # must not raise

    @pytest.mark.asyncio
    async def test_task_calls_operator_notification(self):
        """Task calls send_operator_notification when lead is found."""
        from src.integrations.tasks import send_notification_emails
        from unittest.mock import AsyncMock

        lead_id = uuid.uuid4()
        mock_lead = _make_lead()
        mock_lead.id = lead_id

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_lead)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("src.integrations.tasks.get_session_factory", return_value=mock_factory):
            with patch("src.integrations.tasks.EmailService") as MockService:
                mock_instance = MagicMock()
                MockService.return_value = mock_instance

                await send_notification_emails(lead_id, "demo")

        mock_instance.send_operator_notification.assert_called_once_with(mock_lead, "demo")

    @pytest.mark.asyncio
    async def test_operator_failure_does_not_skip_lead_confirmation(self):
        """If the Operator Notification raises, the Lead Confirmation is still sent.

        The two emails are independent: a fault in one must not suppress the other.
        """
        from src.integrations.tasks import send_notification_emails
        from unittest.mock import AsyncMock

        lead_id = uuid.uuid4()
        mock_lead = _make_lead()
        mock_lead.id = lead_id

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_lead)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("src.integrations.tasks.get_session_factory", return_value=mock_factory):
            with patch("src.integrations.tasks.EmailService") as MockService:
                mock_instance = MagicMock()
                mock_instance.send_operator_notification.side_effect = RuntimeError("boom")
                MockService.return_value = mock_instance

                await send_notification_emails(lead_id, "demo")  # must not raise

        mock_instance.send_lead_confirmation.assert_called_once_with(mock_lead, "demo")


# ── Multipart HTML email (Cycles: _send + wiring) ────────────────────────────

class TestSendHtmlParam:
    """_send() passes 'html' key to Resend when an html body is provided."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def test_send_includes_html_in_payload_when_provided(self):
        service = _make_service()
        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service._send(to="a@b.com", subject="S", text="plain text", html="<p>html</p>")

        payload = mock_httpx.post.call_args.kwargs["json"]
        assert payload.get("html") == "<p>html</p>"
        assert payload.get("text") == "plain text"

    def test_send_omits_html_key_when_not_provided(self):
        service = _make_service()
        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service._send(to="a@b.com", subject="S", text="plain only")

        payload = mock_httpx.post.call_args.kwargs["json"]
        assert "html" not in payload


class TestOperatorNotificationMultipart:
    """send_operator_notification sends a multipart email with HTML body."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def test_operator_notification_includes_html_in_payload(self):
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        html = payload.get("html", "")
        assert "<!DOCTYPE html" in html
        assert lead.nome in html

    def test_operator_notification_preserves_plain_text_body(self):
        service = _make_service()
        lead = _make_lead()

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_operator_notification(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        assert len(payload.get("text", "")) > 50


class TestLeadConfirmationMultipart:
    """send_lead_confirmation sends a multipart email with HTML body."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def _fake_booking(self, url="https://cal.eu/deepsearch/demo"):
        return MagicMock(booking_url=url)

    def test_demo_confirmation_includes_html_with_lead_name(self):
        service = _make_service()
        lead = _make_lead(nome="Giulia Bianchi")

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=self._fake_booking()):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        html = payload.get("html", "")
        assert "<!DOCTYPE html" in html
        assert "Giulia Bianchi" in html

    def test_demo_confirmation_html_includes_booking_url(self):
        service = _make_service()
        lead = _make_lead()
        booking_url = "https://cal.eu/deepsearch/demo-slot"

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=self._fake_booking(booking_url)):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        payload = mock_httpx.post.call_args.kwargs["json"]
        html = payload.get("html", "")
        assert booking_url in html

    @pytest.mark.parametrize("request_type", ["contact", "generic_request"])
    def test_non_demo_confirmation_includes_html(self, request_type):
        service = _make_service()
        lead = _make_lead(nome="Marco Bello")

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, request_type)

        payload = mock_httpx.post.call_args.kwargs["json"]
        html = payload.get("html", "")
        assert "<!DOCTYPE html" in html
        assert "Marco Bello" in html


class TestLeadConfirmationLocale:
    """Lead Confirmation HTML language follows lead.locale."""

    def setup_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def teardown_method(self):
        from src.core.config import get_settings
        get_settings.cache_clear()

    def test_italian_locale_sends_italian_html(self):
        service = _make_service()
        lead = _make_lead(nome="Giulia Bianchi")
        lead.locale = "it"

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "contact")

        html = mock_httpx.post.call_args.kwargs["json"].get("html", "")
        assert "lang=\"it\"" in html
        assert "Richiesta ricevuta" in html

    def test_english_locale_sends_english_html(self):
        service = _make_service()
        lead = _make_lead(nome="John Smith")
        lead.locale = "en"

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "contact")

        html = mock_httpx.post.call_args.kwargs["json"].get("html", "")
        assert "lang=\"en\"" in html
        assert "Request received" in html

    def test_english_locale_plain_text_is_english(self):
        service = _make_service()
        lead = _make_lead(nome="John Smith")
        lead.locale = "en"

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "contact")

        text = mock_httpx.post.call_args.kwargs["json"].get("text", "")
        assert "Thank you" in text
        assert "Grazie" not in text

    def test_missing_locale_defaults_to_italian(self):
        service = _make_service()
        lead = _make_lead()
        lead.locale = None

        with patch("src.integrations.email.service.httpx") as mock_httpx:
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "contact")

        html = mock_httpx.post.call_args.kwargs["json"].get("html", "")
        assert "lang=\"it\"" in html

    def test_english_demo_plain_text_includes_book_slot_phrase(self):
        service = _make_service()
        lead = _make_lead()
        lead.locale = "en"
        booking_url = "https://cal.eu/deepsearch/demo"

        with patch("src.integrations.email.service.httpx") as mock_httpx, \
             patch("src.integrations.email.service.generate_booking_link",
                   return_value=MagicMock(booking_url=booking_url)):
            mock_httpx.post.return_value = MagicMock(raise_for_status=MagicMock())
            service.send_lead_confirmation(lead, "demo")

        text = mock_httpx.post.call_args.kwargs["json"].get("text", "")
        assert booking_url in text
        assert "book" in text.lower()
