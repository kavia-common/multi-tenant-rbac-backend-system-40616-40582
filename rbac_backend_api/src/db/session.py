"""
Database engine and session management using SQLAlchemy 2.0 style.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.config import get_settings

settings = get_settings()

# Create SQLAlchemy engine
engine = create_engine(
    settings.sql_alchemy_dsn,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

# Create sessionmaker
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# PUBLIC_INTERFACE
@contextmanager
def session_scope() -> Generator:
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
