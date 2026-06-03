"""Request ID middleware — analytics & observability (T053).

Responsibilities per request:
  1. Generate (or accept) an `X-Request-ID` UUID header.
  2. Echo the request ID back in the response headers.
  3. Inject `request_id`, `endpoint`, and `locale` into `RequestContext`
     context vars so they appear in all log entries for this request.
  4. Emit a structured post-response analytics log line per request
     (T053: endpoint, method, status_code, duration_ms, locale, request_id).

The locale is extracted from the `Accept-Language` header and resolved to
one of the supported locales: en, it, ar. Defaults to 'it'.

PII GUARANTEE: this middleware NEVER logs request/response body content.
Only metadata (URL path, method, status code, timing) is captured.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging import RequestContext, get_logger

logger = get_logger(__name__)

SUPPORTED_LOCALES = ("en", "it", "ar")
DEFAULT_LOCALE = "it"

# Paths excluded from analytics logging (high-frequency noise)
_SKIP_ANALYTICS_PATHS = frozenset({"/health", "/favicon.ico"})


def _resolve_locale(accept_language: str | None) -> str:
    """Parse Accept-Language header and return the best supported locale.

    Handles simple tags ("it", "en-US", "ar") — no quality weights.
    Falls back to DEFAULT_LOCALE if nothing matches.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    for part in accept_language.split(","):
        # Strip quality weight (e.g. "en-US;q=0.9" → "en-US")
        lang_tag = part.strip().split(";")[0].strip().lower()
        # Try exact match first, then language subtag prefix
        for locale in SUPPORTED_LOCALES:
            if lang_tag == locale or lang_tag.startswith(locale + "-"):
                return locale

    return DEFAULT_LOCALE


class RequestIDMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that assigns and propagates a request ID.

    Also emits post-response structured analytics logs (T053).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 1. Determine request ID (accept client-supplied, else generate)
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # 2. Resolve locale from Accept-Language
        locale = _resolve_locale(request.headers.get("Accept-Language"))

        # 3. Store in context vars so all log statements in this request include them
        RequestContext.set(
            request_id=request_id,
            endpoint=str(request.url.path),
            locale=locale,
        )

        # 4. Start timer
        start_time = time.perf_counter()

        # 5. Process the request
        response = await call_next(request)

        # 6. Compute duration
        duration_ms = round((time.perf_counter() - start_time) * 1000, 1)

        # 7. Echo request ID in response headers
        response.headers["X-Request-ID"] = request_id

        # 8. Post-response analytics log (T053)
        # Skip health-check noise but log all real API calls.
        path = str(request.url.path)
        if path not in _SKIP_ANALYTICS_PATHS:
            logger.info(
                "http_request",
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                locale=locale,
                request_id=request_id,
                # NOTE: never log request body, headers with secrets, or PII fields
            )

        return response
