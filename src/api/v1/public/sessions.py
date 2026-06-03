"""Public session initialization endpoint.

POST /api/v1/sessions

Creates an anonymous session at chatbot open time so engagement data is
associated with a server-side record before lead submission.

No authentication required — the only caller is the DeepSearch frontend widget.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.logging import get_logger
from src.models.session import Session
from src.schemas.errors import problem_503

router = APIRouter(tags=["sessions"])
logger = get_logger(__name__)


class SessionInitRequest(BaseModel):
    locale: str = Field(default="it", max_length=10)
    source_flow: str | None = Field(default=None, max_length=50)


class SessionInitResponse(BaseModel):
    session_id: uuid.UUID
    created_at: datetime


@router.post(
    "/sessions",
    response_model=SessionInitResponse,
    status_code=201,
    summary="Initialize a visitor session",
    description=(
        "Creates an anonymous session record when the chatbot widget opens. "
        "Returns a session_id that the frontend must include in the subsequent "
        "lead capture request to link the session with the lead."
    ),
)
async def init_session(
    body: SessionInitRequest,
    db: AsyncSession = Depends(get_db),
) -> SessionInitResponse | JSONResponse:
    try:
        session = Session(
            locale=body.locale,
            source_flow=body.source_flow,
            engagement_depth=0,
        )
        db.add(session)
        await db.flush()

        logger.info("session_initialized", session_id=str(session.id), locale=body.locale)

        return SessionInitResponse(
            session_id=session.id,
            created_at=session.created_at,
        )

    except OperationalError as exc:
        logger.error("session_init_db_unavailable", error=str(exc))
        return JSONResponse(
            status_code=503,
            content=problem_503(
                detail="Service temporarily unavailable. Please retry.",
                instance="/api/v1/sessions",
            ).model_dump(exclude_none=True),
        )
