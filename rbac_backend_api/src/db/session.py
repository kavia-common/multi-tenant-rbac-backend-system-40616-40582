"""
Database engine and session management using SQLAlchemy 2.0 style.
Import-safe: no DB connections are attempted at module import time.

Behavior:
- Engine and SessionFactory are created lazily.
- No engine.connect() or SELECT 1 at import; connectivity checked only when dependency get_db() is invoked.
- If DB is misconfigured/unavailable, get_db() raises HTTPException 503.

Public interfaces:
- session_scope() context manager
- SessionLocal() factory accessor (kept for backward compatibility)
- get_db() FastAPI dependency
"""

from contextlib import contextmanager
from typing import Generator, Optional
import os
import logging
import time

from fastapi import HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.core.config import get_settings

logger = logging.getLogger(__name__)

# Globals initialized lazily on first use
_engine = None  # type: Optional[object]
_SessionLocal = None  # type: Optional[sessionmaker]
_first_connect_attempt_logged = False  # guard to avoid noisy logs on every request


def _build_dsn_from_env() -> Optional[str]:
    """
    Attempt to construct a MySQL DSN from standard MYSQL_* environment variables if settings sql_alchemy_dsn is missing.
    """
    host = os.getenv("MYSQL_HOST") or os.getenv("MYSQL_URL") or os.getenv("DB_HOST") or "localhost"
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB")
    port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306"

    if user and database:
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
    return None


def _create_engine_and_session_factory() -> None:
    """Internal helper to create engine and Session factory without testing connectivity."""
    global _engine, _SessionLocal
    if _engine is not None and _SessionLocal is not None:
        return
    settings = get_settings()
    # Prefer DB_DSN (settings.sql_alchemy_dsn) then MYSQL_* fallbacks
    dsn = settings.sql_alchemy_dsn or _build_dsn_from_env()
    if not dsn:
        logger.warning("Database DSN not configured (DB_DSN or MYSQL_*). Engine will not be created yet.")
        return
    try:
        safe_tail = dsn.split("@")[-1]
        logger.info("Creating SQLAlchemy engine (lazy) with DSN: mysql+pymysql://****:****@%s", safe_tail)
    except Exception:
        logger.info("Creating SQLAlchemy engine with DSN from configuration.")
    try:
        _engine = create_engine(
            dsn,
            pool_pre_ping=True,   # ensures invalid pooled connections are detected
            pool_recycle=3600,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
    except Exception as exc:
        # Leave engineNone to trigger 503 in dependency; log exception for observability
        logger.exception("Failed to create SQLAlchemy engine: %s", exc)
        _engine = None
        _SessionLocal = None


def _ensure_session_factory_available_or_503() -> None:
    """
    Ensure Session factory exists and database is at least reachable by a lightweight ping.
    Only raise 503 if:
      - We have no DSN configured (engine/session factory missing), or
      - engine.connect() fails (OperationalError/SQLAlchemyError).
    """
    global _first_connect_attempt_logged
    # Ensure factory exists
    if _engine is None or _SessionLocal is None:
        _create_engine_and_session_factory()
        if _engine is None or _SessionLocal is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database is not configured or unavailable",
            )

    # Connectivity probe on first request and thereafter at minimal cost
    try:
        assert _engine is not None
        start = time.time()
        with _engine.connect() as conn:  # type: ignore[union-attr]
            # Very cheap ping to confirm ability to execute any statement
            conn.execute(text("SELECT 1"))
        took = (time.time() - start) * 1000.0
        # Log first successful connectivity to aid troubleshooting
        if not _first_connect_attempt_logged:
            _first_connect_attempt_logged = True
            logger.info("Database connectivity OK on first use (%.1f ms).", took)
    except (OperationalError, SQLAlchemyError) as exc:
        # Log full details on first failure to help root cause analysis
        logger.exception("Database connectivity check failed on first use: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured or unavailable",
        )


# PUBLIC_INTERFACE
@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    _ensure_session_factory_available_or_503()
    assert _SessionLocal is not None  # for type checkers
    db: Session = _SessionLocal()
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
    """Return a SQLAlchemy session factory, ensuring engine is initialized (may raise HTTP 503 on failure)."""
    _ensure_session_factory_available_or_503()
    return _SessionLocal


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session from the shared SessionFactory; returns 503 if DB is unavailable."""
    _ensure_session_factory_available_or_503()
    assert _SessionLocal is not None
    db: Session = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
