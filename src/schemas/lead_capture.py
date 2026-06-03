"""Pydantic v2 schemas for the lead capture endpoint.

POST /api/v1/leads/capture request and response.

Backward Compatibility (T027):
  The `QualificationIn` model includes a `model_validator(mode='before')` that
  maps legacy frontend field names to canonical names. This shim is active for
  the 30-day transition window and logs a deprecation warning per use.

  Legacy → Canonical mapping:
    subject_type → target
    motivation   → obiettivo
    country      → geografia
    user_role    → role

  Constitution Principle X: breaking changes require a 90-day deprecation window.
  This shim satisfies that requirement for the field naming change.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from src.core.logging import get_logger

logger = get_logger(__name__)


# ── Contact ────────────────────────────────────────────────────────────────────

class ContactIn(BaseModel):
    """Contact PII collected at form submission.

    SECURITY: These values MUST NOT appear in application logs.
    """

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Full name of the contact (required)",
    )
    azienda: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company / organisation name (required)",
    )
    email: EmailStr = Field(
        ...,
        description="Contact email address (required, validated format)",
    )
    telefono: str | None = Field(
        default=None,
        max_length=50,
        description="Phone number (optional)",
    )
    ruolo: str | None = Field(
        default=None,
        max_length=100,
        description="Job title / role description (optional, free text)",
    )
    paese: str | None = Field(
        default=None,
        max_length=100,
        description="Country (optional)",
    )
    note: str | None = Field(
        default=None,
        max_length=10000,
        description="Additional notes from the lead (optional, max 10,000 chars)",
    )

    @field_validator("nome", "azienda")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field must not be blank")
        return stripped


# ── Qualification ─────────────────────────────────────────────────────────────

# Legacy field names sent by the current frontend (DemoForm.jsx pre-migration)
_LEGACY_TO_CANONICAL: dict[str, str] = {
    "subject_type": "target",
    "motivation": "obiettivo",
    "country": "geografia",
    "user_role": "role",
    # Additional legacy aliases seen in flowD/flowG
    "func_role": "func_role",           # kept in extra_qualification
    "interest": "interest",             # kept in extra_qualification
    "need_type": "need_type",           # kept in extra_qualification
    "request_nature": "request_nature", # kept in extra_qualification
}

# Fields that are canonical and should NOT be treated as extra
_CANONICAL_FIELDS = frozenset({"target", "obiettivo", "geografia", "role"})

# Extra fields that are known but non-canonical (stored in extra_qualification)
_KNOWN_EXTRA_FIELDS = frozenset({"func_role", "interest", "need_type", "source_flow"})


class QualificationIn(BaseModel):
    """Canonical qualification fields from the funnel.

    Accepts both canonical names (target/obiettivo/geografia/role) and
    legacy names (subject_type/motivation/country/user_role) via backward
    compat shim.

    Unknown extra fields are stored in extra_qualification JSONB on the Lead.
    """

    model_config = ConfigDict(extra="allow")

    target: str | None = Field(
        default=None,
        max_length=50,
        description="Investigation target: 'azienda' or 'persona'",
    )
    obiettivo: str | None = Field(
        default=None,
        max_length=100,
        description="Investigation purpose: due_diligence, aml, hiring, etc.",
    )
    geografia: str | None = Field(
        default=None,
        max_length=100,
        description="Geographic scope",
    )
    role: str | None = Field(
        default=None,
        max_length=100,
        description="User function: legal, compliance, hr, management, other",
    )

    @model_validator(mode="before")
    @classmethod
    def remap_legacy_field_names(cls, data: Any) -> Any:
        """Map legacy frontend field names to canonical names.

        This shim supports the 30-day transition window while DemoForm.jsx
        is updated to use canonical field names.

        Logs a deprecation warning when legacy names are detected.
        """
        if not isinstance(data, dict):
            return data

        legacy_found: list[str] = []
        canonical_map = {
            "subject_type": "target",
            "motivation": "obiettivo",
            "country": "geografia",
            "user_role": "role",
        }

        for legacy_key, canonical_key in canonical_map.items():
            if legacy_key in data and canonical_key not in data:
                data[canonical_key] = data.pop(legacy_key)
                legacy_found.append(f"{legacy_key} -> {canonical_key}")
            elif legacy_key in data and canonical_key in data:
                # Both present — canonical wins, drop the legacy key
                data.pop(legacy_key)
                legacy_found.append(f"{legacy_key} (ignored, canonical present)")

        if legacy_found:
            logger.warning(
                "qualification_legacy_field_names_detected",
                remapped=legacy_found,
                message=(
                    "Deprecated qualification field names detected. "
                    "Please update DemoForm.jsx to use canonical names: "
                    "target, obiettivo, geografia, role. "
                    "This shim will be removed in v1.1."
                ),
            )

        return data

    def get_extra_qualification(self) -> dict[str, Any]:
        """Return non-canonical extra fields for JSONB storage."""
        canonical = {"target", "obiettivo", "geografia", "role"}
        extras = {}
        for key, value in (self.model_extra or {}).items():
            if key not in canonical and value is not None:
                extras[key] = value
        return extras


# ── Events ────────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    """A single funnel event emitted by the frontend."""

    model_config = ConfigDict(extra="ignore")

    event_id: uuid.UUID = Field(
        ...,
        description="Client-generated UUID; stable across retries for deduplication",
    )
    event_type: str = Field(
        ...,
        max_length=100,
        description="Dot-namespaced event type: session.started, funnel.step_completed, etc.",
    )
    event_payload: dict[str, Any] | None = Field(
        default=None,
        description="Event-type-specific data",
    )
    sequence_number: int = Field(
        ...,
        ge=0,
        description="Zero-based ordering index within the session",
    )
    occurred_at: datetime = Field(
        ...,
        description="Client-reported timestamp when the event occurred (ISO 8601)",
    )
    locale: str | None = Field(
        default=None,
        max_length=10,
        description="Locale active when the event was emitted",
    )


# ── Session Metadata ──────────────────────────────────────────────────────────

class MetadataIn(BaseModel):
    """Optional session metadata from the frontend."""

    model_config = ConfigDict(extra="allow")

    session_duration_seconds: int | None = Field(default=None, ge=0)
    engagement_depth: int | None = Field(default=None, ge=0)
    source_flow: str | None = Field(default=None, max_length=50)
    visited_screens: list[str] | None = Field(default=None)
    intent_signals: dict[str, int] | None = Field(default=None)


# ── Request & Response ────────────────────────────────────────────────────────

class LeadCaptureRequest(BaseModel):
    """Full request body for POST /api/v1/leads/capture.

    The `note` field is accepted at the TOP LEVEL of the request body to match
    the current DemoForm.jsx frontend payload shape, which sends:
      { contact: {...}, qualification: {...}, metadata: {...}, note: "..." }

    Root-level `note` takes precedence over `contact.note` when both are present.
    """

    model_config = ConfigDict(extra="ignore")

    contact: ContactIn
    qualification: QualificationIn = Field(default_factory=QualificationIn)
    events: list[EventIn] = Field(default_factory=list)
    metadata: MetadataIn = Field(default_factory=MetadataIn)
    note: str | None = Field(
        default=None,
        max_length=10000,
        description=(
            "Additional notes from the lead (optional). "
            "Mirrors the top-level 'note' field sent by DemoForm.jsx. "
            "Takes precedence over contact.note when both are provided."
        ),
    )
    locale: str = Field(
        default="it",
        max_length=10,
        description="BCP-47 locale tag (en / it / ar)",
    )
    session_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional session_id returned by POST /api/v1/sessions. "
            "When provided, the lead is linked to the pre-created session "
            "instead of creating a new one."
        ),
    )
    idempotency_key: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional client-generated UUID for idempotent submission. "
            "If provided, a second submission with the same key returns "
            "the existing lead without creating a duplicate."
        ),
    )

    @property
    def resolved_note(self) -> str | None:
        """Return the effective note: root-level takes precedence over contact.note."""
        return self.note or self.contact.note


class LeadCaptureResponse(BaseModel):
    """Response body for a successful lead capture."""

    status: str = Field(default="captured")
    session_id: uuid.UUID
    lead_id: uuid.UUID
    created_at: datetime
