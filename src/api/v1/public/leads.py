"""Public lead capture endpoint.

POST /api/v1/leads/capture

Rate limited: 5 requests / 10 minutes per IP.
No authentication required.

Error handling:
  422 — Pydantic validation failure (field-level RFC 7807)
  429 — Rate limit exceeded (RFC 7807 + Retry-After)
  503 — Database unavailable (RFC 7807)
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.logging import get_logger
from src.middleware.rate_limit import CAPTURE_LIMIT, limiter
from src.schemas.errors import problem_422, problem_503
from src.schemas.lead_capture import LeadCaptureRequest, LeadCaptureResponse
from src.services.lead_capture import capture_lead

router = APIRouter(tags=["leads"])
logger = get_logger(__name__)


@router.post(
    "/leads/capture",
    response_model=LeadCaptureResponse,
    summary="Capture a qualified lead",
    description=(
        "Atomically persists a visitor session, lead, and funnel events "
        "from a demo request form submission. "
        "Idempotent: submitting with the same idempotency_key returns the existing lead."
    ),
    responses={
        200: {"description": "Lead captured successfully", "model": LeadCaptureResponse},
        422: {"description": "Validation error"},
        429: {"description": "Rate limit exceeded"},
        503: {"description": "Database unavailable"},
    },
)
@limiter.limit(CAPTURE_LIMIT)
async def capture_lead_endpoint(
    request: Request,
    body: LeadCaptureRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> LeadCaptureResponse | JSONResponse:
    """Accept a demo request from the qualification funnel."""
    try:
        response = await capture_lead(db=db, request=body)

        # Commit the session NOW so the CRM sync background task always finds
        # the lead in the database.  FastAPI's BackgroundTasks can fire before
        # the get_db dependency commits, causing a race condition.
        await db.commit()

        # Optional CRM sync in background — never blocks the response
        from src.integrations.tasks import sync_lead_to_crm
        background_tasks.add_task(sync_lead_to_crm, response.lead_id)

        return response

    except IntegrityError as exc:
        logger.warning("lead_capture_integrity_error", error=str(exc))
        detail = problem_422(
            detail="A data integrity constraint was violated. Please check your submission.",
            instance="/api/v1/leads/capture",
        )
        return JSONResponse(
            status_code=422,
            content=detail.model_dump(exclude_none=True),
        )

    except OperationalError as exc:
        logger.error("lead_capture_db_unavailable", error=str(exc))
        detail = problem_503(
            detail=(
                "The service is temporarily unavailable. "
                "Your data has not been lost — please retry in a few minutes."
            ),
            instance="/api/v1/leads/capture",
        )
        return JSONResponse(
            status_code=503,
            content=detail.model_dump(exclude_none=True),
        )

    except Exception as exc:
        logger.error(
            "lead_capture_unexpected_error",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        detail = problem_503(
            detail="An unexpected error occurred. Please try again.",
            instance="/api/v1/leads/capture",
        )
        return JSONResponse(
            status_code=503,
            content=detail.model_dump(exclude_none=True),
        )
