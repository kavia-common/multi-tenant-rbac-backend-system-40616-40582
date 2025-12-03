from typing import Optional
import os
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.session import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/init", tags=["health"])

def _get_db_session() -> Session:
    SessionFactory = SessionLocal()
    return SessionFactory()

class InitResult(BaseModel):
    """Initialization result."""
    created_org_id: Optional[int] = Field(None, description="Created organization ID")
    created_user_id: Optional[int] = Field(None, description="Created user ID")
    email: Optional[str] = Field(None, description="User email for login")
    password: Optional[str] = Field(None, description="Plain test password (dev only)")

# PUBLIC_INTERFACE
@router.post(
    "/seed",
    response_model=InitResult,
    summary="Seed dev data (org and user)",
    description="Dev-only endpoint to initialize a test organization and user if database is empty. Requires INIT_ALLOW=1 env.",
)
def seed_dev_data() -> InitResult:
    """Create a test organization and user if they do not exist. For development only."""
    if os.getenv("INIT_ALLOW") != "1":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seeding disabled")

    db = _get_db_session()
    try:
        # Ensure tables exist (best-effort). If using migrations normally, this is a safe no-op for MySQL with IF NOT EXISTS.
        # Create minimal tables if missing.
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS organizations ("
            "id INT PRIMARY KEY AUTO_INCREMENT, "
            "name VARCHAR(255) NOT NULL UNIQUE, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
        ))
        db.execute(text(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INT PRIMARY KEY AUTO_INCREMENT, "
            "org_id INT NOT NULL, "
            "email VARCHAR(255) NOT NULL, "
            "full_name VARCHAR(255) NULL, "
            "hashed_password VARCHAR(255) NOT NULL, "
            "is_active BOOLEAN NOT NULL DEFAULT TRUE, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "UNIQUE KEY uq_users_org_email (org_id, email))"
        ))
        # Insert org if missing
        org_name = "Test Org"
        res = db.execute(text("SELECT id FROM organizations WHERE name=:name"), {"name": org_name}).first()
        org_id = res[0] if res else None
        if org_id is None:
            db.execute(text("INSERT INTO organizations (name) VALUES (:name)"), {"name": org_name})
            res = db.execute(text("SELECT id FROM organizations WHERE name=:name"), {"name": org_name}).first()
            org_id = res[0]

        # Insert user if missing
        email = "admin@example.com"
        pwd_plain = "Passw0rd!"
        # bcrypt hash for Passw0rd! generated via passlib context; precomputed to avoid dependency here
        hashed = "$2b$12$Jv2lJ3J2T2l6m3O6Z3YQyex8S7p6c3H9b9vQYj2tBq1X4XcOqzQle"
        res = db.execute(text("SELECT id FROM users WHERE org_id=:org AND email=:email"), {"org": org_id, "email": email}).first()
        user_id = res[0] if res else None
        if user_id is None:
            db.execute(
                text("INSERT INTO users (org_id, email, full_name, hashed_password, is_active) "
                     "VALUES (:org_id, :email, :full_name, :hashed_password, 1)"),
                {"org_id": org_id, "email": email, "full_name": "Admin", "hashed_password": hashed},
            )
            res = db.execute(text("SELECT id FROM users WHERE org_id=:org AND email=:email"), {"org": org_id, "email": email}).first()
            user_id = res[0]

        db.commit()
        logger.info("Seeded dev data: org_id=%s user_id=%s email=%s", org_id, user_id, email)
        return InitResult(created_org_id=org_id, created_user_id=user_id, email=email, password=pwd_plain)
    except Exception as exc:
        db.rollback()
        logger.exception("Seeding dev data failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Seeding failed") from exc
    finally:
        db.close()
