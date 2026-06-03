"""RFC 7807 Problem Details error schemas.

All API error responses use this format for consistency.
See: https://datatracker.ietf.org/doc/html/rfc7807

Usage::

    from src.schemas.errors import problem_422, problem_429, problem_503
    raise HTTPException(status_code=422, detail=problem_422(...).model_dump())
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    """Describes a single validation error on a specific field."""

    field: str = Field(..., description="Dot-path to the invalid field (e.g. 'contact.email')")
    message: str = Field(..., description="Human-readable error description")


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response body.

    Used for ALL error responses: 422, 429, 503, and any future error codes.
    """

    type: str = Field(
        ...,
        description="URI reference identifying the problem type",
        examples=["https://deepsearch.io/errors/validation-error"],
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem",
        examples=["Validation Error"],
    )
    status: int = Field(
        ...,
        description="HTTP status code",
        examples=[422],
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation of this specific occurrence",
    )
    instance: str | None = Field(
        default=None,
        description="URI reference identifying this specific occurrence (e.g. request path)",
    )
    errors: list[FieldError] | None = Field(
        default=None,
        description="Per-field validation errors (present for 422 responses)",
    )
    retry_after: int | None = Field(
        default=None,
        alias="retry_after",
        description="Seconds to wait before retrying (present for 429 responses)",
    )

    model_config = {"populate_by_name": True}


# ── Factory helpers ───────────────────────────────────────────────────────────

BASE_URI = "https://deepsearch.io/errors"


def problem_422(
    detail: str,
    errors: list[FieldError] | None = None,
    instance: str | None = None,
) -> ProblemDetail:
    """Create a 422 Unprocessable Entity problem detail."""
    return ProblemDetail(
        type=f"{BASE_URI}/validation-error",
        title="Validation Error",
        status=422,
        detail=detail,
        instance=instance,
        errors=errors,
    )


def problem_429(
    detail: str = "Rate limit exceeded. Please slow down your requests.",
    retry_after: int = 60,
    instance: str | None = None,
) -> ProblemDetail:
    """Create a 429 Too Many Requests problem detail."""
    return ProblemDetail(
        type=f"{BASE_URI}/rate-limit-exceeded",
        title="Too Many Requests",
        status=429,
        detail=detail,
        instance=instance,
        retry_after=retry_after,
    )


def problem_503(
    detail: str = "Service temporarily unavailable. Please try again shortly.",
    instance: str | None = None,
) -> ProblemDetail:
    """Create a 503 Service Unavailable problem detail."""
    return ProblemDetail(
        type=f"{BASE_URI}/service-unavailable",
        title="Service Unavailable",
        status=503,
        detail=detail,
        instance=instance,
    )


def problem_401(
    detail: str = "Authentication required.",
    instance: str | None = None,
) -> ProblemDetail:
    """Create a 401 Unauthorized problem detail."""
    return ProblemDetail(
        type=f"{BASE_URI}/unauthorized",
        title="Unauthorized",
        status=401,
        detail=detail,
        instance=instance,
    )


def problem_404(
    detail: str = "Resource not found.",
    instance: str | None = None,
) -> ProblemDetail:
    """Create a 404 Not Found problem detail."""
    return ProblemDetail(
        type=f"{BASE_URI}/not-found",
        title="Not Found",
        status=404,
        detail=detail,
        instance=instance,
    )


def pydantic_errors_to_field_errors(validation_errors: list[dict[str, Any]]) -> list[FieldError]:
    """Convert Pydantic v2 ValidationError.errors() list to FieldError list."""
    result = []
    for err in validation_errors:
        loc = err.get("loc", ())
        field = ".".join(str(part) for part in loc) if loc else "body"
        message = err.get("msg", "Invalid value")
        result.append(FieldError(field=field, message=message))
    return result
