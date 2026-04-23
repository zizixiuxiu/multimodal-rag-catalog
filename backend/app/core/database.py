"""Database session management."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create engine with connection pooling
engine = create_engine(
    str(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=settings.DEBUG,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """Ensure pgvector is available on connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cursor.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database sessions (for scripts/background tasks)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
