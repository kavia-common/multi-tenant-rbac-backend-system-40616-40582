"""
Database engine and session management using SQLAlchemy 2.0 style.
Handles absence of configured DB DSN gracefully by delaying engine creation.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import get_settings

settings = get_settings()

# Engine and session factory are created lazily to allow app startup without DB configured.
_engine = None  # type: Optional[object]
_SessionLocal = None  # type: Optional[sessionmaker]


def _ensure_engine():
    """Create engine and sessionmaker if DSN is available; otherwise raise a clear error on usage."""
    global _engine, _SessionLocal
    if _engine is None or _SessionLocal is None:
        dsn = settings.sql_alchemy_dsn
        if not dsn:
            raise RuntimeError(
                "Database is not configured. Set DB_DSN or provide db_connection.txt and restart. "
                "See .env.example for details."
            )
        _engine = create_engine(
            dsn,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


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
