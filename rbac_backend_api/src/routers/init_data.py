from typing import Optional, Dict, List
import os
import logging
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, SQLAlchemyError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect

from src.core.config import get_settings
from src.db.session import session_scope, get_db
from src.models.organization import Organization
from src.models.user import User
from src.models.role import Role
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole
from src.security.auth import get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

class InitResult(BaseModel):
    """Initialization result."""
    created_org_id: Optional[int] = Field(None, description="Created organization ID")
    created_user_id: Optional[int] = Field(None, description="Created user ID")
    email: Optional[str] = Field(None, description="User email for login")
    password: Optional[str] = Field(None, description="Plain test password (dev only)")

class InitError(BaseModel):
    """Structured initialization error details."""
    error: str = Field(..., description="High-level error category")
    cause: str = Field(..., description="Root cause message")
    hints: List[str] = Field(default_factory=list, description="Suggested remediation steps")

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
            detail=InitError(
                error="forbidden",
                cause=f"Seeding disabled. INIT_ALLOW={init_allow!r}",
                hints=["Set INIT_ALLOW=1 in environment and retry."],
            ).model_dump(),
        )

def _assert_config_preconditions() -> None:
    """
    Validate env configuration: DB DSN derivation and JWT secret presence.
    Do not hard fail on JWT in dev, but return clear guidance.
    """
    settings = get_settings()
    # DB DSN presence check across all supported sources
    dsn_sources = {
        "settings.sql_alchemy_dsn": bool(settings.sql_alchemy_dsn),
        "DB_DSN": bool(os.getenv("DB_DSN")),
        "MYSQL_*": bool(os.getenv("MYSQL_USER") and os.getenv("MYSQL_DB")),
        "DB_CONNECTION_FILE": bool(os.getenv("DB_CONNECTION_FILE")),
    }
    if not any(dsn_sources.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=InitError(
                error="db_dsn_missing",
                cause="Database DSN not configured.",
                hints=[
                    "Provide DB_DSN env or",
                    "Set DB_CONNECTION_FILE or",
                    "Set MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB",
                    "See .env.example and schema_setup.sh in the repo.",
                ],
            ).model_dump(),
        )

    # JWT secret presence check (warn but allow for dev)
    if not settings.jwt.secret_key or settings.jwt.secret_key == "change_me_in_env":
        logger.warning("JWT_SECRET_KEY is missing or default; using insecure default for dev only.")

def _check_required_tables(db: Session) -> None:
    """
    Ensure all required tables exist; if missing, raise 409 with guidance to run migrations/setup.
    """
    required_tables = {
        "organizations",
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "audit_logs",
    }
    try:
        inspector = inspect(db.bind)
        existing = set(inspector.get_table_names())
    except Exception as exc:
        logger.exception("Failed to inspect database schema.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=InitError(
                error="db_inspection_failed",
                cause=f"Could not inspect schema: {exc.__class__.__name__}",
                hints=[
                    "Verify database is reachable and user has metadata privileges.",
                    "Check DB_DSN/MYSQL_* settings.",
                ],
            ).model_dump(),
        ) from exc

    missing = sorted(list(required_tables - existing))
    if missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=InitError(
                error="db_schema_missing",
                cause=f"Required tables missing: {', '.join(missing)}",
                hints=[
                    "Run schema_setup.sh against the configured database.",
                    "Ensure your MySQL user has privileges to create tables.",
                ],
            ).model_dump(),
        )

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
    perms_by_name: Dict[str, Permission] = {}
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
        200: {"description": "Seeded successfully"},
        403: {"description": "Seeding disabled (INIT_ALLOW not set)", "model": InitError},
        409: {"description": "Schema missing; run setup first", "model": InitError},
        503: {"description": "Database unreachable or misconfigured", "model": InitError},
        500: {"description": "Seeding failed due to server error", "model": InitError},
    },
    tags=["health"],
)
# PUBLIC_INTERFACE
def seed_dev_data(db_dep: Session | None = Depends(get_db)) -> InitResult:
    logger.info("Handling POST /api/init/seed (INIT_ALLOW=%s)", os.getenv("INIT_ALLOW"))
    """Seed dev organization, admin user, roles and permissions.

    Public API:
    - Method: POST /api/init/seed
    - Response (200): JSON with {created_org_id, created_user_id, email, password}
    - Error responses:
      403: Seeding disabled when INIT_ALLOW != "1"
      503: Database unreachable/misconfigured
      409: Required schema/tables missing
      500: Unexpected server or SQL errors

    Notes:
    - Uses unified get_db dependency to ensure the global engine/session is initialized consistently.
    - Actual transaction handled via session_scope to keep operation atomic. The db_dep is accepted to
      initialize the shared Session factory and for alignment with other routes.
    """
    _ensure_init_allowed()
    _assert_config_preconditions()

    defaults = SeedDefaults()
    try:
        # Ensure session connectivity and transactional behavior happen via session_scope
        with session_scope() as db:
            # Connectivity test and schema presence checks
            try:
                db.execute(text("SELECT 1"))
            except OperationalError as ping_exc:
                logger.exception("Connectivity test failed before seeding.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=InitError(
                        error="db_connection_failed",
                        cause=f"DB connection failed: {ping_exc.__class__.__name__}",
                        hints=[
                            "Verify DB_DSN or MYSQL_* environment variables.",
                            "Ensure the database service is reachable from the API container.",
                        ],
                    ).model_dump(),
                ) from ping_exc
            except ProgrammingError as ping_exc:
                # ProgrammingError may indicate schema/database issues
                logger.exception("Programming error on DB ping; likely schema missing.")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=InitError(
                        error="db_schema_missing",
                        cause=f"DB ping raised ProgrammingError: {str(ping_exc)}",
                        hints=["Run schema_setup.sh against the configured database."],
                    ).model_dump(),
                ) from ping_exc
            except Exception as ping_exc:
                logger.exception("Unexpected error during DB ping.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=InitError(
                        error="db_connection_failed",
                        cause=f"DB ping failed: {ping_exc.__class__.__name__}",
                        hints=["Check DSN configuration and DB service status."],
                    ).model_dump(),
                ) from ping_exc

            # Schema validation
            _check_required_tables(db)

            result = _seed_core_entities(db, defaults)
            logger.info("Seed endpoint completed successfully: org_id=%s user_id=%s", result.created_org_id, result.created_user_id)
            return result
    except HTTPException:
        raise
    except IntegrityError as exc:
        logger.exception("Seeding failed due to SQL integrity error")
        msg = str(getattr(exc.orig, "args", ["integrity error"])[0])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=InitError(
                error="integrity_error",
                cause=msg,
                hints=["Check for conflicting unique constraints with existing seed data."],
            ).model_dump(),
        ) from exc
    except OperationalError as exc:
        logger.exception("Seeding failed due to DB connectivity/operational error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=InitError(
                error="db_connection_failed",
                cause=f"OperationalError: {str(exc.orig) if hasattr(exc, 'orig') else str(exc)}",
                hints=["Verify DB service, network, and credentials."],
            ).model_dump(),
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Seeding failed due to SQLAlchemy error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=InitError(
                error="sqlalchemy_error",
                cause=exc.__class__.__name__,
                hints=["Inspect server logs for full stacktrace."],
            ).model_dump(),
        ) from exc
    except Exception as exc:
        logger.exception("Seeding failed due to unexpected error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=InitError(
                error="unexpected_error",
                cause=exc.__class__.__name__,
                hints=["Inspect server logs for details."],
            ).model_dump(),
        ) from exc
