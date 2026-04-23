"""Pytest configuration — ensures tests use an isolated test database.

This prevents test data cleanup from wiping the development/production database.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Step 1: Override DATABASE_URL to use test DB BEFORE app modules are imported ──
# Parse the original DATABASE_URL and swap the database name
_original_url = os.environ.get("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5433/multimodal_rag")

# Replace last path component (database name) with 'multimodal_rag_test'
if "/" in _original_url:
    _base = _original_url.rsplit("/", 1)[0]  # everything before last /
    _test_url = f"{_base}/multimodal_rag_test"
else:
    _test_url = _original_url

os.environ["DATABASE_URL"] = _test_url
os.environ.setdefault("APP_ENV", "test")


def pytest_sessionstart(session):
    """Create test database and tables before any tests run."""
    from sqlalchemy import create_engine, text

    # Extract connection info from test URL
    test_url = os.environ["DATABASE_URL"]
    # Parse: postgresql+psycopg2://user:pass@host:port/dbname
    rest = test_url.replace("postgresql+psycopg2://", "")
    creds_host, dbname = rest.rsplit("/", 1)
    # Connect to 'postgres' maintenance DB to create test DB
    maint_url = f"postgresql+psycopg2://{creds_host}/postgres"
    maint_engine = create_engine(maint_url, isolation_level="AUTOCOMMIT")

    with maint_engine.connect() as conn:
        # Check if test DB exists
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": dbname},
        ).fetchone()
        if not result:
            conn.execute(text(f'CREATE DATABASE "{dbname}"'))
            print(f"\n🆕 Created test database: {dbname}")
        else:
            print(f"\n✅ Test database exists: {dbname}")

    maint_engine.dispose()

    # Enable pgvector extension in test DB
    test_engine_tmp = create_engine(test_url, isolation_level="AUTOCOMMIT")
    with test_engine_tmp.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    test_engine_tmp.dispose()

    # ── Override already-loaded settings & recreate engine ──
    # app modules may have been imported before conftest ran (e.g. by pytest plugins)
    # Force the test URL into settings and rebuild the engine.
    from app.core import config
    config.settings.DATABASE_URL = test_url  # type: ignore[assignment]

    from app.core import database
    database.engine.dispose()
    database.engine = create_engine(
        test_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    database.SessionLocal.configure(bind=database.engine)

    # Create tables in test DB
    from app.models.base import Base
    Base.metadata.create_all(bind=database.engine)
    print("✅ Test tables created\n")
