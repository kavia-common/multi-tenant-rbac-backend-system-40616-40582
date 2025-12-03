from typing import Optional
import os
import logging
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.core.config import get_settings
from src.db.session import session_scope
from src.models.organization import Organization
from src.models.user import User
from src.models.role import Role
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole
from src.security.auth import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/init", tags=["health"])

class InitResult(BaseModel):
    """Initialization result."""
    created_org_id: Optional[int] = Field(None, description="Created organization ID")
    created_user_id: Optional[int] = Field(None, description="Created user ID")
    email: Optional[str] = Field(None, description="User email for login")
    password: Optional[str] = Field(None, description="Plain test password (dev only)")

@dataclass
class SeedDefaults:
    org_name: str = "Test Org"
    email: str = "admin@example.com"
    full_name: str = "Admin"
    password: str = "Passw0rd!"

def _ensure_init_allowed() -> None:
    """Validate seeding is allowed via INIT_ALLOW env flag and log details."""
    init_allow = os.getenv("INIT_ALLOW")
    if init_allow != "1":
        logger.warning("Attempt to call /api/init/seed while INIT_ALLOW=%s", init_allow)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seeding disabled. Set INIT_ALLOW=1 in environment to enable.",
        )

def _assert_config_preconditions() -> None:
    """
    Validate core configuration before hitting the database so we can fail fast with specific reasons.
    Also perform a lightweight connectivity test (SELECT 1) to ensure DB is reachable before seeding.
    """
    settings = get_settings()
    # DB DSN presence check; detailed message if missing
    if not (settings.sql_alchemy_dsn or os.getenv("DB_DSN") or os.getenv("MYSQL_USER")):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DB not configured: Set DB_DSN, DB_CONNECTION_FILE, or MYSQL_* env vars.",
        )
    # JWT secret presence check (warn but allow with explicit message)
    if not settings.jwt.secret_key or settings.jwt.secret_key == "change_me_in_env":
        logger.warning("JWT_SECRET_KEY is missing or default; using insecure default for dev only.")
        # do not fail hard for seeding, but include in logs

def _seed_core_entities(db: Session, defaults: SeedDefaults) -> InitResult:
    """
    Seed organization, admin user (with bcrypt hash), essential roles and permissions.
    Operation is idempotent: existing records will be reused.
    Wrapped by transactional session_scope in the endpoint.
    """
    # Organization
    org = db.query(Organization).filter(Organization.name == defaults.org_name).one_or_none()
    if not org:
        org = Organization(name=defaults.org_name)
        db.add(org)
        db.flush()  # assign id

    # User
    user = (
        db.query(User)
        .filter(User.org_id == org.id, User.email == defaults.email)
        .one_or_none()
    )
    if not user:
        user = User(
            org_id=org.id,
            email=defaults.email,
            full_name=defaults.full_name,
            hashed_password=get_password_hash(defaults.password),
            is_active=True,
        )
        db.add(user)
        db.flush()

    # Roles
    role_admin = (
        db.query(Role)
        .filter(Role.org_id == org.id, Role.name == "admin")
        .one_or_none()
    )
    if not role_admin:
        role_admin = Role(org_id=org.id, name="admin", description="Organization administrator")
        db.add(role_admin)
        db.flush()

    role_user = (
        db.query(Role)
        .filter(Role.org_id == org.id, Role.name == "user")
        .one_or_none()
    )
    if not role_user:
        role_user = Role(org_id=org.id, name="user", description="Standard user")
        db.add(role_user)
        db.flush()

    # Permissions (minimal set)
    perm_names = [
        "users:read", "users:write",
        "roles:read", "roles:write",
        "permissions:read", "permissions:write",
        "audit:read",
    ]
    perms_by_name = {}
    for pname in perm_names:
        perm = (
            db.query(Permission)
            .filter(Permission.org_id == org.id, Permission.name == pname)
            .one_or_none()
        )
        if not perm:
            perm = Permission(org_id=org.id, name=pname, description=pname)
            db.add(perm)
            db.flush()
        perms_by_name[pname] = perm

    # Assign all permissions to admin role
    for perm in perms_by_name.values():
        rp = (
            db.query(RolePermission)
            .filter(RolePermission.role_id == role_admin.id, RolePermission.permission_id == perm.id)
            .one_or_none()
        )
        if not rp:
            db.add(RolePermission(role_id=role_admin.id, permission_id=perm.id))

    # Ensure admin user has admin role
    ur = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_id == role_admin.id)
        .one_or_none()
    )
    if not ur:
        db.add(UserRole(user_id=user.id, role_id=role_admin.id))

    logger.info("Seeding successful or already present: org_id=%s user_id=%s", org.id, user.id)
    return InitResult(
        created_org_id=org.id,
        created_user_id=user.id,
        email=user.email,
        password=defaults.password,
    )

# PUBLIC_INTERFACE
@router.post(
    "/seed",
    response_model=InitResult,
    summary="Seed dev data (org and user)",
    description="Dev-only endpoint to initialize a test organization and user if database is empty. Requires INIT_ALLOW=1 env.",
    operation_id="seed_dev_data_api_init_seed_post",
    responses={
        200: {"description": "Seeded successfully", "model": InitResult},
        403: {"description": "Seeding disabled (INIT_ALLOW not set)"},
        503: {"description": "Database unreachable or misconfigured"},
        500: {"description": "Seeding failed due to server error"},
    },
)
def seed_dev_data() -> InitResult:
    """
    Seed development data.

    This creates a default organization, an admin user with a bcrypt-hashed password,
    essential roles and permissions, and assigns admin role to the admin user.
    It is idempotent: running multiple times will not duplicate data.

    Returns:
        InitResult: created or existing IDs, plus dev email/password.

    Raises:
        HTTPException: 403 if disabled, or mapped errors with specific causes.
    """
    _ensure_init_allowed()
    _assert_config_preconditions()

    defaults = SeedDefaults()
    try:
        # Ensure session connectivity and transactional behavior happen via session_scope
        with session_scope() as db:
            # Connectivity test at session level to provide clearer error if schema missing/unreachable
            try:
                # simple SELECT 1 ensures connection and current schema accessibility
                db.execute(text("SELECT 1"))
            except Exception as ping_exc:
                logger.exception("Connectivity test failed before seeding.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database unreachable or schema not accessible.",
                ) from ping_exc

            result = _seed_core_entities(db, defaults)
            return result
    except HTTPException:
        raise
    except IntegrityError as exc:
        logger.exception("Seeding failed due to SQL integrity error")
        # surface table name/constraint if present, but avoid leaking sensitive info
        msg = str(getattr(exc.orig, "args", ["integrity error"])[0])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seeding failed: SQL integrity error ({msg})",
        ) from exc
    except OperationalError as exc:
        logger.exception("Seeding failed due to DB connectivity/operational error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable or misconfigured (OperationalError).",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Seeding failed due to SQLAlchemy error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seeding failed: SQL error ({exc.__class__.__name__})",
        ) from exc
    except Exception as exc:
        logger.exception("Seeding failed due to unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Seeding failed: {exc.__class__.__name__}",
        ) from exc
