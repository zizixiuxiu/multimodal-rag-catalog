"""SQLAlchemy base model with common fields and utilities."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps."""

    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
