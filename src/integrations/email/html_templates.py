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

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


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
        "source_flow": extra.get("source_flow"),
        "request_type_label": type_label,
        "nome": lead.nome,
        "azienda": lead.azienda,
        "email": lead.email,
        "telefono": lead.telefono,
        "ruolo": lead.ruolo,
        "paese": lead.paese,
        "subject_type": lead.target,
        "intent": lead.obiettivo,
        "request_nature": extra.get("request_nature"),
        "func_role": lead.role,
        "geo_area": lead.geografia,
        "need_type": extra.get("need_type"),
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
    context = {
        "request_type": request_type,
        "nome": lead.nome,
        "azienda": lead.azienda,
        "intent": lead.obiettivo,
        "request_nature": extra.get("request_nature"),
        "booking_url": booking_url,
    }
    template_name = _CLIENT_TEMPLATES.get(lang, "client.it.html.j2")
    return _env.get_template(template_name).render(**context)
