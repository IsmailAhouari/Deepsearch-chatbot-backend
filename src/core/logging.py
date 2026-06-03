"""Structlog configuration for structured JSON logging.

SECURITY: PII fields (nome, email, azienda, telefono, phone, name, company)
MUST NEVER appear in log output. The `PII_FIELDS` set is used by the
`redact_pii_processor` to strip them before any renderer sees them.

Usage::

    from src.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("lead_captured", session_id=str(session_id), lead_id=str(lead_id))
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

# ── PII field names that MUST NOT appear in logs ──────────────────────────────
PII_FIELDS: frozenset[str] = frozenset(
    {
        "nome", "name", "email", "email_address",
        "azienda", "company", "company_name",
        "telefono", "phone", "phone_number",
        "note", "notes",
        "ruolo",        # job title — may contain PII context
    }
)

# ── Request-scoped context variables ─────────────────────────────────────────
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_session_id_var: ContextVar[str] = ContextVar("session_id", default="")
_endpoint_var: ContextVar[str] = ContextVar("endpoint", default="")
_locale_var: ContextVar[str] = ContextVar("locale", default="it")


class RequestContext:
    """Helpers for reading and writing request-scoped log context."""

    @staticmethod
    def set(
        request_id: str = "",
        session_id: str = "",
        endpoint: str = "",
        locale: str = "it",
    ) -> None:
        _request_id_var.set(request_id)
        _session_id_var.set(session_id)
        _endpoint_var.set(endpoint)
        _locale_var.set(locale)

    @staticmethod
    def get() -> dict[str, str]:
        return {
            "request_id": _request_id_var.get(),
            "session_id": _session_id_var.get(),
            "endpoint": _endpoint_var.get(),
            "locale": _locale_var.get(),
        }


# ── Custom processors ─────────────────────────────────────────────────────────

def _add_logger_name(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Add logger name to the event dict, compatible with PrintLogger and stdlib Logger.

    ``structlog.stdlib.add_logger_name`` calls ``logger.name`` which only exists on
    stdlib ``logging.Logger`` instances.  Since we use ``PrintLoggerFactory``, that
    attribute is absent and raises AttributeError.  This replacement handles both
    cases gracefully.
    """
    record = event_dict.get("_record")
    if record is not None:
        event_dict.setdefault("logger", record.name)
    else:
        name = getattr(logger, "name", None)
        if name:
            event_dict.setdefault("logger", name)
    return event_dict


def _inject_request_context(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Inject request-scoped fields from context vars into every log record."""
    ctx = RequestContext.get()
    if ctx["request_id"]:
        event_dict.setdefault("request_id", ctx["request_id"])
    if ctx["session_id"]:
        event_dict.setdefault("session_id", ctx["session_id"])
    if ctx["endpoint"]:
        event_dict.setdefault("endpoint", ctx["endpoint"])
    if ctx["locale"]:
        event_dict.setdefault("locale", ctx["locale"])
    return event_dict


def _redact_pii(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Remove any PII fields before the event is rendered.

    Constitution Principle VII: PII MUST NEVER appear in structured logs.
    """
    for field in PII_FIELDS:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    return event_dict


# ── Configuration ─────────────────────────────────────────────────────────────

def configure_logging(environment: str = "development", log_level: str = "INFO") -> None:
    """Configure structlog for the application.

    Call this once at application startup (in the lifespan handler).
    JSON renderer is used in production/staging; human-friendly console
    renderer is used in development.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        _add_logger_name,  # guard-safe replacement for structlog.stdlib.add_logger_name
        structlog.processors.TimeStamper(fmt="iso"),
        _inject_request_context,
        _redact_pii,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if environment in ("production", "staging"):
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        # No file= arg: PrintLoggerFactory() evaluates sys.stdout lazily each time
        # the factory is invoked, instead of capturing a reference at configure time.
        # This prevents "I/O operation on closed file" errors in tests where
        # pytest's capfd temporarily replaces sys.stdout between test cases.
        logger_factory=structlog.PrintLoggerFactory(),
        # False: invoke the factory on every log call so we always get the
        # current sys.stdout rather than a frozen reference to a closed fd.
        cache_logger_on_first_use=False,
    )

    # Also configure stdlib logging to go through structlog (for third-party libs)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name.

    Usage::

        logger = get_logger(__name__)
        logger.info("event_name", key="value")
    """
    return structlog.get_logger(name)
