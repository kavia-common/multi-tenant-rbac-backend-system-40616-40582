"""
FastAPI dependencies for authentication and authorization (RBAC).
Provides current_user, organization context, and role/permission checks.
"""

from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.user import User
from src.models.user_role import UserRole
from src.models.role import Role
from src.models.role_permission import RolePermission
from src.models.permission import Permission
from src.security.auth import decode_access_token

reuseable_oauth2 = HTTPBearer(auto_error=True)


def get_db():
    """Yield a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# PUBLIC_INTERFACE
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(reuseable_oauth2),
    db: Session = Depends(get_db),
) -> User:
    """Extract current user from JWT and fetch from DB."""
    token = credentials.credentials
    payload = decode_access_token(token)
    user_id = int(payload.get("sub"))
    org_id = int(payload.get("org_id"))
    user = db.execute(select(User).where(User.id == user_id, User.org_id == org_id)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return user


# PUBLIC_INTERFACE
def require_permission(permission_name: str) -> Callable:
    """
    Dependency factory to check that current user has a specific permission within their org.
    """

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # Query permissions for current_user via roles
        stmt = (
            select(Permission.name)
            .select_from(UserRole)
            .join(Role, UserRole.role_id == Role.id)
            .join(RolePermission, Role.id == RolePermission.role_id)
            .join(Permission, RolePermission.permission_id == Permission.id)
            .where(UserRole.user_id == current_user.id, Permission.org_id == current_user.org_id)
        )
        names = {row[0] for row in db.execute(stmt).all()}
        if permission_name not in names:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return dependency


# PUBLIC_INTERFACE
def require_role(role_name: str) -> Callable:
    """
    Dependency factory to ensure current user has a given role in their org.
    """

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        stmt = (
            select(Role.name)
            .select_from(UserRole)
            .join(Role, UserRole.role_id == Role.id)
            .where(UserRole.user_id == current_user.id, Role.org_id == current_user.org_id)
        )
        names = {row[0] for row in db.execute(stmt).all()}
        if role_name not in names:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Required role not held")

    return dependency
