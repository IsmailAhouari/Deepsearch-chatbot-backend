"""HTML email rendering via Jinja2.

Renders the operator notification and client confirmation HTML emails from a
Lead. The rendered HTML is sent as the `html` part of a multipart email
alongside the existing plain-text bodies (see ``service.py``).

Placeholder mapping note (operator template):
The original hand-authored template used the legacy tokens ``INTEREST`` and
``FUNC_ROLE``. Those concepts were unified during the qualification-ID
normalization work — ``role`` replaces ``funcRole``, and the flowF
"contact reason" now lives in ``extra_qualification.request_nature``. The
template variables here map to the *current* Lead schema.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


_SOURCE_FLOW_LABELS: dict[str, dict[str, str]] = {
    "it": {
        "platform_overview":    "Panoramica piattaforma",
        "use_cases":            "Casi d'uso",
        "personas":             "A chi si rivolge",
        "demo_request":         "Richiedi demo",
        "contact_team":         "Contatta il team",
        "commercial_info":      "Informazioni commerciali",
        "custom_request":       "Altro",
        "direct_qualification": "Qualificazione diretta",
    },
    "en": {
        "platform_overview":    "Platform Overview",
        "use_cases":            "Use Cases",
        "personas":             "Who It's For",
        "demo_request":         "Request a Demo",
        "contact_team":         "Contact the Team",
        "commercial_info":      "Commercial Information",
        "custom_request":       "Other",
        "direct_qualification": "Direct Qualification",
    },
}

_QUALIFICATION_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "it": {
        "target": {
            "aziende": "Aziende",
            "persone": "Persone",
        },
        "intent": {
            "due_diligence": "Due Diligence",
            "partner_selection": "Selezione partner affari",
            "aml": "Analisi AML",
            "risk_analysis": "Analisi del rischio",
            "supplier_check": "Verifica fornitori",
            "litigation": "Litigation intelligence",
            "reputational_risk": "Rischio reputazionale",
            "hiring": "Assunzione dipendente",
            "other": "Altro",
            "counterparty_risk": "Rischio controparti",
            "corporate_investigations": "Indagini aziendali",
        },
        "role": {
            "security_risk": "Security / Risk",
            "legal": "Legale / Contenzioso",
            "compliance_aml": "Compliance / AML",
            "HR": "HR",
            "management": "Direzione / Board",
            "investor": "Investitore / Fondo",
            "other": "Altro",
            "risk_management": "Risk Management",
            "investigations": "Investigazioni",
        },
        "request_nature": {
            "commercial": "Commerciale",
            "partnership": "Partnership",
            "platform_demo": "Presentazione piattaforma",
            "technical_request": "Richiesta tecnica",
        },
        "need_type": {
            "immediate_project": "Progetto immediato",
            "platform_evaluation": "Valutazione piattaforma",
            "internal_analysis": "Analisi interna",
            "commercial_info": "Informazioni commerciali",
        },
        "sub_context": {
            "supplier": "Fornitore",
            "client": "Cliente",
            "partner": "Partner",
            "investment_target": "Target di investimento",
            "civil_litigation": "Contenzioso civile",
            "commercial_dispute": "Disputa commerciale",
            "asset_tracing": "Asset tracing",
            "pre_litigation": "Pre-contenzioso",
            "other": "Altro",
        },
    },
    "en": {
        "target": {
            "aziende": "Companies",
            "persone": "Individuals",
        },
        "intent": {
            "due_diligence": "Due Diligence",
            "partner_selection": "Business Partner Selection",
            "aml": "AML Analysis",
            "risk_analysis": "Risk Analysis",
            "supplier_check": "Supplier Verification",
            "litigation": "Litigation Intelligence",
            "reputational_risk": "Reputational Risk",
            "hiring": "Employee Hiring",
            "other": "Other",
            "counterparty_risk": "Counterparty Risk",
            "corporate_investigations": "Corporate Investigations",
        },
        "role": {
            "security_risk": "Security / Risk",
            "legal": "Legal / Litigation",
            "compliance_aml": "Compliance / AML",
            "HR": "HR",
            "management": "Management / Board",
            "investor": "Investor / Fund",
            "other": "Other",
            "risk_management": "Risk Management",
            "investigations": "Investigations",
        },
        "request_nature": {
            "commercial": "Commercial",
            "partnership": "Partnership",
            "platform_demo": "Platform Demo",
            "technical_request": "Technical Request",
        },
        "need_type": {
            "immediate_project": "Immediate Project",
            "platform_evaluation": "Platform Evaluation",
            "internal_analysis": "Internal Analysis",
            "commercial_info": "Commercial Information",
        },
        "sub_context": {
            "supplier": "Supplier",
            "client": "Client",
            "partner": "Partner",
            "investment_target": "Investment Target",
            "civil_litigation": "Civil Litigation",
            "commercial_dispute": "Commercial Dispute",
            "asset_tracing": "Asset Tracing",
            "pre_litigation": "Pre-Litigation",
            "other": "Other",
        },
    },
}


def _resolve_source_flow_label(raw_flow: str | None, lang: str = "it") -> "Markup | None":
    """Resolve a source_flow ID to the UI-facing label in the given language.

    Returns a Markup-safe string so Jinja2 autoescape does not mangle
    typographic characters (e.g. the apostrophe in "Casi d'uso").
    """
    if raw_flow is None:
        return None
    lang_map = _SOURCE_FLOW_LABELS.get(lang, _SOURCE_FLOW_LABELS["it"])
    return Markup(lang_map.get(raw_flow, raw_flow))


def _resolve_qual_label(value: str | None, category: str, lang: str = "it") -> str | None:
    """Resolve a qualification ID to a human-readable label.

    Falls back to: Italian labels when lang is unknown, raw value when ID not found.
    Returns None when value is None.
    """
    if value is None:
        return None
    lang_labels = _QUALIFICATION_LABELS.get(lang, _QUALIFICATION_LABELS["it"])
    return lang_labels.get(category, {}).get(value, value)


def _format_received_at(lead: object) -> str:
    """Format the Lead's created_at for display; empty string if unavailable."""
    created = getattr(lead, "created_at", None)
    if isinstance(created, datetime):
        return created.strftime("%d/%m/%Y %H:%M")
    return ""


def render_operator_html(lead: object, request_type: str, type_label: str) -> str:
    """Render the Operator Notification HTML body."""
    extra = getattr(lead, "extra_qualification", None) or {}
    context = {
        "data_ora": _format_received_at(lead),
        "source_flow": _resolve_source_flow_label(extra.get("source_flow"), "it"),
        "request_type_label": type_label,
        "nome": lead.nome,
        "azienda": lead.azienda,
        "email": lead.email,
        "telefono": lead.telefono,
        "ruolo": lead.ruolo,
        "paese": lead.paese,
        "subject_type": _resolve_qual_label(lead.target, "target"),
        "intent": _resolve_qual_label(lead.obiettivo, "intent"),
        "request_nature": _resolve_qual_label(extra.get("request_nature"), "request_nature"),
        "func_role": _resolve_qual_label(lead.role, "role"),
        "geo_area": lead.geografia,
        "need_type": _resolve_qual_label(extra.get("need_type"), "need_type"),
        "sub_context": _resolve_qual_label(extra.get("sub_context"), "sub_context"),
        "note": lead.note,
    }
    return _env.get_template("operator.html.j2").render(**context)


_CLIENT_TEMPLATES: dict[str, str] = {
    "it": "client.it.html.j2",
    "en": "client.en.html.j2",
}


def render_client_html(
    lead: object,
    request_type: str,
    booking_url: str | None,
    lang: str = "it",
) -> str:
    """Render the Lead Confirmation HTML body sent to the Lead.

    ``booking_url`` is the Booking Link (cal.eu) when available; the CTA is
    omitted when it is ``None``.
    ``lang`` selects the template language ('en' or 'it'); unknown codes fall
    back to Italian.
    """
    extra = getattr(lead, "extra_qualification", None) or {}
    lang_key = lang if lang in _QUALIFICATION_LABELS else "it"
    context = {
        "request_type": request_type,
        "nome": lead.nome,
        "azienda": lead.azienda,
        "intent": _resolve_qual_label(lead.obiettivo, "intent", lang_key),
        "request_nature": _resolve_qual_label(extra.get("request_nature"), "request_nature", lang_key),
        "sub_context": _resolve_qual_label(extra.get("sub_context"), "sub_context", lang_key),
        "booking_url": booking_url,
    }
    template_name = _CLIENT_TEMPLATES.get(lang, "client.it.html.j2")
    return _env.get_template(template_name).render(**context)
