"""TDD — HTML email template integration.

Renders the operator notification and client confirmation HTML templates
(Jinja2) from a Lead. These are sent as the `html` part of a multipart email
alongside the existing plain-text bodies (which remain unchanged).

Scope: ONLY the new HTML rendering. The plain-text builders
(_build_operator_body, _build_demo_confirmation_body, _build_plain_confirmation_body)
must not be modified by this work.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.integrations.email.html_templates import (
    render_client_html,
    render_operator_html,
)


def make_lead(**overrides) -> MagicMock:
    lead = MagicMock()
    lead.id = "abc12345-0000-0000-0000-000000000000"
    lead.nome = "Giulia Bianchi"
    lead.azienda = "TechCorp Srl"
    lead.email = "giulia@techcorp.it"
    lead.telefono = "+39 02 1234567"
    lead.ruolo = "Head of Compliance"
    lead.paese = "Italia"
    lead.target = "aziende"
    lead.obiettivo = "due_diligence"
    lead.geografia = "Svizzera"
    lead.role = "compliance_aml"
    lead.note = "Interessati a una valutazione su 3 controparti."
    lead.extra_qualification = {
        "request_nature": "commercial",
        "need_type": "immediate_project",
        "source_flow": "use_cases",
    }
    for k, v in overrides.items():
        setattr(lead, k, v)
    return lead


# ── Operator HTML ─────────────────────────────────────────────────────────────

class TestOperatorHtml:
    def test_renders_contact_fields_into_html(self):
        html = render_operator_html(make_lead(), "demo", "Demo Request")
        assert "<!DOCTYPE html" in html
        assert "Giulia Bianchi" in html
        assert "TechCorp Srl" in html
        assert "giulia@techcorp.it" in html

    def test_renders_qualification_fields(self):
        html = render_operator_html(make_lead(), "demo", "Demo Request")
        assert "due_diligence" in html      # obiettivo / intent
        assert "commercial" in html         # request_nature
        assert "compliance_aml" in html     # func_role
        assert "Svizzera" in html           # geo_area
        assert "immediate_project" in html  # need_type
        assert "aziende" in html            # subject_type

    def test_renders_note_section(self):
        html = render_operator_html(make_lead(), "demo", "Demo Request")
        assert "Interessati a una valutazione su 3 controparti." in html

    def test_omits_note_section_when_absent(self):
        lead = make_lead(note=None)
        html = render_operator_html(lead, "contact", "Contact")
        assert "Note / Richiesta" not in html

    def test_shows_dash_when_telefono_missing(self):
        lead = make_lead(telefono=None)
        html = render_operator_html(lead, "demo", "Demo Request")
        assert "Non fornito" in html

    def test_shows_dash_when_ruolo_missing(self):
        lead = make_lead(ruolo=None)
        html = render_operator_html(lead, "demo", "Demo Request")
        assert "Non specificato" in html

    def test_qualification_section_hidden_when_all_fields_absent(self):
        lead = make_lead(obiettivo=None, role=None, target=None, geografia=None)
        lead.extra_qualification = {}
        html = render_operator_html(lead, "demo", "Demo Request")
        assert "Profilo di Qualificazione" not in html

    def test_request_type_label_in_badge(self):
        html = render_operator_html(make_lead(), "demo", "Richiesta Demo")
        assert "Richiesta Demo" in html

    def test_source_flow_shown_when_present(self):
        html = render_operator_html(make_lead(), "demo", "Demo Request")
        assert "use_cases" in html

    def test_source_flow_absent_when_missing(self):
        lead = make_lead()
        lead.extra_qualification = {}
        html = render_operator_html(lead, "demo", "Demo Request")
        assert "Flusso" not in html


# ── Client HTML ───────────────────────────────────────────────────────────────

class TestClientHtml:
    def test_renders_lead_name(self):
        html = render_client_html(make_lead(), "demo", "https://cal.eu/deepsearch/demo")
        assert "Giulia Bianchi" in html

    def test_demo_variant_shows_booking_cta(self):
        html = render_client_html(make_lead(), "demo", "https://cal.eu/deepsearch/demo")
        assert "https://cal.eu/deepsearch/demo" in html
        assert "Prenota Demo" in html

    def test_contact_variant_no_booking_cta(self):
        html = render_client_html(make_lead(), "contact", None)
        assert "Prenota Demo" not in html
        assert "cal.eu" not in html

    def test_generic_variant_no_booking_cta(self):
        html = render_client_html(make_lead(), "generic", None)
        assert "Prenota Demo" not in html

    def test_booking_cta_omitted_when_url_none_even_for_demo(self):
        html = render_client_html(make_lead(), "demo", None)
        assert "Prenota Demo" not in html

    def test_does_not_mention_calendly(self):
        html = render_client_html(make_lead(), "demo", "https://cal.eu/deepsearch/demo")
        assert "calendly" not in html.lower()
        assert "Calendly" not in html

    # ── Language selection ────────────────────────────────────────────────────

    def test_default_lang_is_italian(self):
        html = render_client_html(make_lead(), "demo", None)
        assert "lang=\"it\"" in html
        assert "Richiesta ricevuta" in html

    def test_lang_it_renders_italian_template(self):
        html = render_client_html(make_lead(), "demo", None, lang="it")
        assert "lang=\"it\"" in html
        assert "Richiesta ricevuta" in html
        assert "Request received" not in html

    def test_lang_en_renders_english_template(self):
        html = render_client_html(make_lead(), "demo", None, lang="en")
        assert "lang=\"en\"" in html
        assert "Request received" in html
        assert "Richiesta ricevuta" not in html

    def test_english_demo_booking_cta_label(self):
        html = render_client_html(make_lead(), "demo", "https://cal.eu/deepsearch/demo", lang="en")
        assert "Book Demo" in html
        assert "Prenota Demo" not in html

    def test_english_demo_hero_copy(self):
        html = render_client_html(make_lead(), "demo", None, lang="en")
        assert "1 business day" in html

    def test_english_contact_hero_copy(self):
        html = render_client_html(make_lead(), "contact", None, lang="en")
        assert "contact request" in html.lower()

    def test_english_next_steps_label(self):
        html = render_client_html(make_lead(), "demo", None, lang="en")
        assert "What happens next" in html

    def test_unknown_lang_falls_back_to_italian(self):
        html = render_client_html(make_lead(), "demo", None, lang="fr")
        assert "lang=\"it\"" in html
