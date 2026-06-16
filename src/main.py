"""FastAPI application factory.

This module creates and configures the FastAPI app instance.
Use `create_app()` to get the configured application — this enables
testing to spin up the app with different settings.

The module-level `app` is what uvicorn loads: `uvicorn src.main:app`.

Authentication: none. The only client is the DeepSearch frontend (HTTPS + CORS).

Startup sequence (lifespan):
  1. Configure structlog (JSON in production, console in development)
  2. Verify DB connectivity (fail loudly if unreachable at startup)

Shutdown sequence (lifespan):
  1. Close SQLAlchemy engine connection pool
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from slowapi import _rate_limit_exceeded_handler  # noqa: F401
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from src.core.config import get_settings
from src.core.database import close_engine, get_session_factory
from src.core.logging import configure_logging, get_logger
from src.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from src.middleware.request_id import RequestIDMiddleware
from src.schemas.errors import (
    pydantic_errors_to_field_errors,
    problem_422,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown logic."""
    settings = get_settings()

    # ── Startup ───────────────────────────────────────────────────────────────
    configure_logging(
        environment=settings.environment,
        log_level=settings.log_level,
    )

    logger.info(
        "application_starting",
        environment=settings.environment,
        log_level=settings.log_level,
        crm_adapter=settings.crm_adapter_class,
        booking_enabled=bool(settings.booking_event_url),
    )

    # Warn about optional email config absent in non-production environments.
    # In production these vars are required (Settings raises at instantiation).
    if not settings.is_production:
        _warn_missing_optional = [
            ("RESEND_API_KEY", settings.resend_api_key),
            ("BOOKING_EVENT_URL", settings.booking_event_url),
            ("INSIDE_NOTIFICATION_EMAIL", settings.inside_notification_email),
            ("EMAIL_FROM_ADDRESS", settings.email_from_address),
        ]
        for var_name, value in _warn_missing_optional:
            if not value:
                logger.warning(
                    "optional_config_absent",
                    variable=var_name,
                    effect="email notifications disabled or degraded",
                )

    # Verify DB is reachable — fail loudly at startup rather than silently
    # later on the first real request.
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("database_connection_verified")
    except Exception as exc:
        logger.error("database_connection_failed_at_startup", error=str(exc))
        # Do NOT prevent startup — Railway health probe must be able to respond.
        # The health endpoint will surface "degraded" status.

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("application_shutting_down")
    await close_engine()
    logger.info("database_engine_closed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="DeepSearch API",
        description=(
            "Lead capture backend for the DeepSearch "
            "conversational qualification system."
        ),
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── State (shared with limiter) ───────────────────────────────────────────
    app.state.limiter = limiter

    # ── Middleware (applied in REVERSE registration order) ────────────────────
    # 1. CORS — must be outermost so preflight requests are handled correctly
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # 2. SlowAPI rate limiting
    app.add_middleware(SlowAPIMiddleware)

    # 3. Request ID injection (must be AFTER slowapi so limiter sees real IP)
    app.add_middleware(RequestIDMiddleware)

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return await rate_limit_exceeded_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle FastAPI request-body validation errors with RFC 7807 format."""
        errors = pydantic_errors_to_field_errors(exc.errors())
        logger.warning(
            "request_validation_failed",
            path=str(request.url.path),
            errors=[{"field": e.field, "message": e.message} for e in errors],
            raw_errors=exc.errors(),
        )
        detail = problem_422(
            detail="Request validation failed.",
            errors=errors,
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=422, content=detail.model_dump(exclude_none=True))

    @app.exception_handler(ValidationError)
    async def _validation_error_handler(request: Request, exc: ValidationError) -> JSONResponse:
        """Handle Pydantic ValidationError raised explicitly inside route handlers."""
        errors = pydantic_errors_to_field_errors(exc.errors())
        detail = problem_422(
            detail="Request validation failed.",
            errors=errors,
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=422, content=detail.model_dump(exclude_none=True))

    # ── Routers ───────────────────────────────────────────────────────────────
    from src.api.health import router as health_router
    app.include_router(health_router)

    from src.api.v1.public.sessions import router as sessions_router
    app.include_router(sessions_router, prefix="/api/v1")

    from src.api.v1.public.leads import router as leads_router
    app.include_router(leads_router, prefix="/api/v1")

    return app


# Module-level app instance — loaded by uvicorn
app = create_app()
