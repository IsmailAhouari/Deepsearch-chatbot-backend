"""TDD — Red phase

These tests fail until issue-017 refactors _build_demo_confirmation_body()
and _build_plain_confirmation_body() to be locale-aware.

Green: implement _get_copy(locale) and update the two body builders.
Refactor: extract _EMAIL_COPY dict to a separate module if it grows beyond ~30 lines.

Scope: ONLY the two Lead Confirmation functions.
_build_operator_body() is NOT tested here — it must not be modified.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

# ── Red: these imports fail until _get_copy is added to service.py ────────────
from src.integrations.email.service import (
    _build_demo_confirmation_body,
    _build_plain_confirmation_body,
    _get_copy,
)


def make_lead(locale: str | None = "it", nome: str = "Marco") -> MagicMock:
    lead = MagicMock()
    lead.locale = locale
    lead.nome = nome
    return lead


# ── _get_copy ─────────────────────────────────────────────────────────────────

class TestGetCopy:
    def test_returns_italian_for_it(self):
        c = _get_copy("it")
        assert "Ciao" in c["greeting"]

    def test_returns_english_for_en(self):
        c = _get_copy("en")
        assert "Hi" in c["greeting"] or "Hello" in c["greeting"]

    def test_falls_back_to_italian_for_none(self):
        c = _get_copy(None)
        assert "Ciao" in c["greeting"]

    def test_falls_back_to_italian_for_unsupported_locale(self):
        c = _get_copy("de")
        assert "Ciao" in c["greeting"]

    def test_falls_back_to_italian_for_empty_string(self):
        c = _get_copy("")
        assert "Ciao" in c["greeting"]


# ── Demo confirmation — Italian ───────────────────────────────────────────────

class TestDemoConfirmationItalian:
    def test_subject_contains_italian(self):
        from src.integrations.email.service import EmailService
        from unittest.mock import patch

        lead = make_lead(locale="it")
        with patch.object(EmailService, "_resolve_booking_url", return_value=None):
            svc = MagicMock(spec=EmailService)
            svc._build_confirmation = EmailService._build_confirmation.__get__(svc)
            svc._resolve_booking_url = MagicMock(return_value=None)
            subject, *_ = svc._build_confirmation(lead, "demo")

        assert "ricevuta" in subject.lower()

    def test_body_greeting_is_italian(self):
        lead = make_lead(locale="it", nome="Marco")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert body.startswith("Ciao Marco,")

    def test_body_contains_italian_copy(self):
        lead = make_lead(locale="it")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "Grazie" in body
        assert "contatterà" in body

    def test_body_signoff_is_italian(self):
        lead = make_lead(locale="it")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "Il team DeepSearch" in body

    def test_body_includes_booking_url_when_present(self):
        lead = make_lead(locale="it")
        body = _build_demo_confirmation_body(lead, booking_url="https://cal.com/example")
        assert "https://cal.com/example" in body

    def test_body_excludes_booking_section_when_none(self):
        lead = make_lead(locale="it")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "https://cal.com" not in body
        assert "contatterà a breve" in body


# ── Demo confirmation — English ───────────────────────────────────────────────

class TestDemoConfirmationEnglish:
    def test_subject_contains_english(self):
        from src.integrations.email.service import EmailService
        from unittest.mock import patch

        lead = make_lead(locale="en")
        with patch.object(EmailService, "_resolve_booking_url", return_value=None):
            svc = MagicMock(spec=EmailService)
            svc._build_confirmation = EmailService._build_confirmation.__get__(svc)
            svc._resolve_booking_url = MagicMock(return_value=None)
            subject, *_ = svc._build_confirmation(lead, "demo")

        assert "received" in subject.lower()

    def test_body_greeting_is_english(self):
        lead = make_lead(locale="en", nome="John")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        first_line = body.split("\n")[0]
        assert "John" in first_line
        assert "Hi" in first_line or "Hello" in first_line

    def test_body_contains_english_copy(self):
        lead = make_lead(locale="en")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "Thank you" in body
        assert "business hours" in body

    def test_body_signoff_is_english(self):
        lead = make_lead(locale="en")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "DeepSearch Team" in body

    def test_body_includes_booking_url_when_present(self):
        lead = make_lead(locale="en")
        body = _build_demo_confirmation_body(lead, booking_url="https://cal.com/example")
        assert "https://cal.com/example" in body

    def test_no_italian_in_english_body(self):
        lead = make_lead(locale="en")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        italian_markers = ["Ciao", "Grazie", "contatterà", "Il team DeepSearch"]
        for marker in italian_markers:
            assert marker not in body, f"Italian string '{marker}' found in English email"


# ── Plain confirmation — Italian ──────────────────────────────────────────────

class TestPlainConfirmationItalian:
    def test_body_greeting_is_italian(self):
        lead = make_lead(locale="it", nome="Lucia")
        body = _build_plain_confirmation_body(lead)
        assert body.startswith("Ciao Lucia,")

    def test_body_contains_italian_thanks(self):
        lead = make_lead(locale="it")
        body = _build_plain_confirmation_body(lead)
        assert "Grazie" in body


# ── Plain confirmation — English ──────────────────────────────────────────────

class TestPlainConfirmationEnglish:
    def test_body_greeting_is_english(self):
        lead = make_lead(locale="en", nome="Sarah")
        body = _build_plain_confirmation_body(lead)
        first_line = body.split("\n")[0]
        assert "Sarah" in first_line
        assert "Hi" in first_line or "Hello" in first_line

    def test_body_contains_english_thanks(self):
        lead = make_lead(locale="en")
        body = _build_plain_confirmation_body(lead)
        assert "Thank you" in body

    def test_no_italian_in_english_body(self):
        lead = make_lead(locale="en")
        body = _build_plain_confirmation_body(lead)
        assert "Ciao" not in body
        assert "Grazie" not in body


# ── Fallback ──────────────────────────────────────────────────────────────────

class TestLocaleEmailFallback:
    def test_none_locale_falls_back_to_italian(self):
        lead = make_lead(locale=None)
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "Ciao" in body

    def test_unsupported_locale_falls_back_to_italian(self):
        lead = make_lead(locale="fr")
        body = _build_demo_confirmation_body(lead, booking_url=None)
        assert "Ciao" in body


# ── Operator body must not be modified ───────────────────────────────────────
# This test verifies _build_operator_body still produces its original Italian+English
# mixed format. If this test fails, someone touched the operator function by mistake.

class TestOperatorBodyUnchanged:
    def test_operator_body_contains_english_section_headers(self):
        from src.integrations.email.service import _build_operator_body

        lead = MagicMock()
        lead.id = "test-id"
        lead.nome = "Mario"
        lead.azienda = "Acme"
        lead.email = "mario@acme.it"
        lead.telefono = "+39 02 1234567"
        lead.ruolo = "Compliance"
        lead.paese = "Italia"
        lead.target = "aziende"
        lead.obiettivo = "due_diligence"
        lead.geografia = "Italia"
        lead.role = "compliance_aml"
        lead.note = None
        lead.extra_qualification = {}

        body = _build_operator_body(lead, "demo", "Demo Request")

        # These English headers are part of the original implementation
        # and must remain unchanged
        assert "── Contact ──" in body
        assert "── Qualification ──" in body
        assert "Name:" in body
        assert "Company:" in body
