"""Health check endpoint.

GET /health — always returns HTTP 200 so Railway's load balancer never
drops the container due to a probe failure. The response body indicates
the actual health of each component.

Railway uses this for both liveness and readiness probes.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from src.core.database import get_session_factory
from src.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)

APP_VERSION = "1.0.0"


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description=(
        "Returns the operational status of the API and its dependencies. "
        "Always returns HTTP 200; check the `status` field for actual health. "
        "status='healthy' means all checks pass. "
        "status='degraded' means DB is unreachable."
    ),
)
async def health_check() -> HealthResponse:
    """Check DB connectivity and return aggregate health status.

    Returns `{"status": "healthy"}` when all checks pass.
    Returns `{"status": "degraded"}` when DB is unreachable — the API is
    still serving but persistence operations will fail.
    """
    from src.core.config import get_settings
    settings = get_settings()

    db_status = "ok"
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        logger.warning("health_check_db_failed", error=str(exc))

    aggregate = "healthy" if db_status == "ok" else "degraded"

    return HealthResponse(
        status=aggregate,
        environment=settings.environment,
        database=db_status,
        version=APP_VERSION,
    )
