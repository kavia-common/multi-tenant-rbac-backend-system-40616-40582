"""
Database engine and session management using SQLAlchemy 2.0 style.
Handles absence of configured DB DSN gracefully by delaying engine creation.

Connectivity verification:
- On first use, runs a lightweight SELECT 1 to ensure the database is reachable.
- Raises RuntimeError with actionable message so API can convert to HTTP 503.
Transactions:
- session_scope wraps operations in a transaction and performs commit/rollback.
"""

from contextlib import contextmanager
from typing import Generator, Optional
import os
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Engine and session factory are created lazily to allow app startup without DB configured.
_engine: Optional[object] = None
_SessionLocal: Optional[sessionmaker] = None
_connectivity_checked: bool = False  # ensure we test connectivity only once on first session creation


def _build_dsn_from_env() -> Optional[str]:
    """
    Attempt to construct a MySQL DSN from standard MYSQL_* environment variables if settings sql_alchemy_dsn is missing.
    This supports local/dev scenarios where db_connection.txt isn't present but env vars are.
    """
    host = os.getenv("MYSQL_HOST") or os.getenv("MYSQL_URL") or os.getenv("DB_HOST") or "localhost"
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB")
    port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306"

    if user and database:
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return None


def _ensure_engine():
    """Create engine and sessionmaker if DSN is available; otherwise raise a clear error on usage."""
    global _engine, _SessionLocal, _connectivity_checked
    if _engine is None or _SessionLocal is None:
        dsn = settings.sql_alchemy_dsn or _build_dsn_from_env()
        if not dsn:
            logger.error("Database DSN not configured. Provide DB_DSN or db_connection.txt or MYSQL_* environment vars.")
            raise RuntimeError(
                "Database is not configured. Set DB_DSN, provide a db_connection.txt, or set MYSQL_* env vars and restart. "
                "See .env.example for details."
            )
        # Log DSN without password for visibility
        try:
            safe_dsn_tail = dsn.split("@")[-1]
            logger.info("Initializing database engine with DSN: mysql+pymysql://****:****@%s", safe_dsn_tail)
        except Exception:
            logger.info("Initializing database engine with DSN from configuration.")
        _engine = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)

    # Lightweight connectivity check once, on first use
    if not _connectivity_checked:
        try:
            with _engine.connect() as conn:  # type: ignore[union-attr]
                conn.execute(text("SELECT 1"))
            _connectivity_checked = True
            logger.info("Database connectivity check succeeded.")
        except OperationalError as exc:
            logger.exception("Database connectivity check failed.")
            # Raise runtime error so API layer can map to 503 with clear message
            raise RuntimeError("DB not configured or unreachable (OperationalError). Check DSN/MYSQL_* and DB service. Verify credentials and host/port.") from exc


# PUBLIC_INTERFACE
@contextmanager
def session_scope() -> Generator:
    """Provide a transactional scope around a series of operations."""
    _ensure_engine()
    assert _SessionLocal is not None  # for type checkers
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# PUBLIC_INTERFACE
def SessionLocal():
    """Return a SQLAlchemy session factory, ensuring engine is initialized.

    Note: This mirrors the previous import style (from src.db.session import SessionLocal)
    so existing code paths keep working.
    """
    _ensure_engine()
    return _SessionLocal
