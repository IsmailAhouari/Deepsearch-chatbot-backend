"""SQLAlchemy declarative base and reusable mixins.

All ORM models inherit from `Base`.
`UUIDMixin` provides a server-generated UUID primary key.
`TimestampMixin` provides `created_at` and `updated_at` columns with
server-side defaults — no Python-side clock calls needed.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Project-wide declarative base.

    Import this in `alembic/env.py` (after importing all model modules) so
    that Alembic can discover the full metadata for autogenerate.
    """


class UUIDMixin:
    """Primary key as a server-generated UUID (gen_random_uuid()).

    Using `server_default` means the DB generates the value; Python never
    calls `uuid.uuid4()` in application code, keeping the models testable
    without a live DB connection for reads.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )


class TimestampMixin:
    """Audit timestamps populated entirely on the database server.

    `created_at`: set once at INSERT time.
    `updated_at`: set at INSERT and updated at every UPDATE via an Alembic-
                  managed trigger (see migration 001_initial_schema).
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
