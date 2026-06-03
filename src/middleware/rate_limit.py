"""Rate limiting configuration using slowapi (Starlette/FastAPI wrapper for limits).

Rate limits (per constitution Principle VII):
  - POST /api/v1/leads/capture: 5 requests / 10 minutes per IP
  - Admin routes:               60 requests / minute per IP

The 429 handler returns an RFC 7807 Problem Details body with a Retry-After
header so clients can implement automatic backoff.
"""
from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from limits.storage import MemoryStorage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.schemas.errors import problem_429

# ── Limiter instance ──────────────────────────────────────────────────────────
# Uses in-memory storage by default. Override with RATE_LIMIT_STORAGE_URL env
# var (e.g. redis://...) for multi-instance deployments.
# The storage_uri is read from the environment by slowapi when set.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],  # no global default — limits are applied per route
    storage_uri=None,   # None → in-memory (set RATE_LIMIT_STORAGE_URL for Redis)
)

# ── Per-route limit strings ───────────────────────────────────────────────────
CAPTURE_LIMIT = "5/10 minutes"
ADMIN_LIMIT = "60/minute"


# ── 429 exception handler ─────────────────────────────────────────────────────
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return RFC 7807 body with Retry-After header when rate limit is hit.

    The visitor's qualification data is NOT lost — they should retry their
    submission after the window resets.
    """
    retry_after = 60  # safe default; slowapi may have finer-grained info
    detail = problem_429(
        detail=(
            "Too many requests. Your submission has not been lost — "
            "please wait before resubmitting."
        ),
        retry_after=retry_after,
        instance=str(request.url.path),
    )
    return JSONResponse(
        status_code=429,
        content=detail.model_dump(exclude_none=True),
        headers={"Retry-After": str(retry_after)},
    )
