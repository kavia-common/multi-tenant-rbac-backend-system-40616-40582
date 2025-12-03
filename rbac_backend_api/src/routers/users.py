from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.audit_log import AuditLog
from src.models.user import User
from src.models.user_role import UserRole
from src.models.role import Role
from src.schemas.user import UserCreate, UserOut
from src.security.auth import get_password_hash
from src.security.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/api/users", tags=["rbac"])

def get_db():
    """Yield a SQLAlchemy session (SessionLocal factory pattern)."""
    SessionFactory = SessionLocal()
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()

def _audit(db: Session, org_id: int, user_id: Optional[int], action: str, resource_type: str, resource_id: Optional[str], details: Optional[str] = None) -> None:
    """Internal helper to write an audit log."""
    log = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=details,
    )
    db.add(log)

class UserUpdate(BaseModel):
    """Payload to update user details (excluding password)."""
    full_name: Optional[str] = Field(None, description="Full name")
    is_active: Optional[bool] = Field(None, description="Is active")

class PasswordReset(BaseModel):
    """Payload to reset a user's password."""
    new_password: str = Field(..., description="New password")

# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Create a user within the caller's organization. Requires 'users:write' permission.",
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> UserOut:
    """Create a user in the same organization as current user; enforce org scoping."""
    if payload.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization operation not allowed")

    existing = db.execute(
        select(User).where(User.org_id == payload.org_id, User.email == payload.email)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists in org")

    user = User(
        org_id=payload.org_id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        is_active=True,
    )
    db.add(user)
    db.flush()
    _audit(db, org_id=user.org_id, user_id=current_user.id, action="create", resource_type="user", resource_id=str(user.id), details=f"Created user {user.email}")
    return UserOut.model_validate(user, from_attributes=True)

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[UserOut],
    summary="List users",
    description="List users within caller's organization. Requires 'users:read' permission.",
)
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:read")),
) -> List[UserOut]:
    """List users in the same organization as current user."""
    rows = db.execute(
        select(User).where(User.org_id == current_user.org_id).order_by(User.id.desc())
    ).scalars().all()
    return [UserOut.model_validate(u, from_attributes=True) for u in rows]

# PUBLIC_INTERFACE
@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get user",
    description="Fetch a user by id within caller's organization. Requires 'users:read' permission.",
)
def get_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:read")),
) -> UserOut:
    """Get a user by id, constrained to caller's org."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user, from_attributes=True)

# PUBLIC_INTERFACE
@router.put(
    "/{user_id}",
    response_model=UserOut,
    summary="Update user",
    description="Update a user's details within caller's organization. Requires 'users:write' permission.",
)
def update_user(
    updates: UserUpdate,
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> UserOut:
    """Update user details (full_name, is_active)."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if updates.full_name is not None:
        user.full_name = updates.full_name
    if updates.is_active is not None:
        user.is_active = updates.is_active

    db.add(user)
    _audit(db, org_id=user.org_id, user_id=current_user.id, action="update", resource_type="user", resource_id=str(user.id), details="Updated user fields")
    return UserOut.model_validate(user, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user within caller's organization. Requires 'users:write' permission.",
)
def delete_user(
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> None:
    """Delete a user in caller's org."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.execute(delete(UserRole).where(UserRole.user_id == user.id))  # cleanup roles
    db.execute(delete(User).where(User.id == user.id))
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="delete", resource_type="user", resource_id=str(user_id), details=f"Deleted user {user.email}")
    return None

# PUBLIC_INTERFACE
@router.post(
    "/{user_id}/roles/{role_id}",
    response_model=UserOut,
    summary="Assign role to user",
    description="Assign a role to a user within the same org. Requires 'users:write' permission.",
)
def assign_role_to_user(
    user_id: int = Path(..., description="User ID"),
    role_id: int = Path(..., description="Role ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> UserOut:
    """Assign role ensuring org scoping."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found in org")
    # Check existing
    existing = db.execute(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    ).scalar_one_or_none()
    if existing:
        return UserOut.model_validate(user, from_attributes=True)
    link = UserRole(user_id=user.id, role_id=role.id)
    db.add(link)
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="assign_role", resource_type="user", resource_id=str(user.id), details=f"Assigned role '{role.name}'")
    return UserOut.model_validate(user, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{user_id}/roles/{role_id}",
    response_model=UserOut,
    summary="Remove role from user",
    description="Remove a role from a user within the same org. Requires 'users:write' permission.",
)
def remove_role_from_user(
    user_id: int = Path(..., description="User ID"),
    role_id: int = Path(..., description="Role ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> UserOut:
    """Remove role from user ensuring org scoping."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found in org")
    db.execute(
        delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
    )
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="remove_role", resource_type="user", resource_id=str(user.id), details=f"Removed role '{role.name}'")
    return UserOut.model_validate(user, from_attributes=True)

# PUBLIC_INTERFACE
@router.post(
    "/{user_id}/reset_password",
    response_model=UserOut,
    summary="Reset user password",
    description="Reset a user's password within the same org. Requires 'users:write' permission.",
)
def reset_user_password(
    payload: PasswordReset,
    user_id: int = Path(..., description="User ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("users:write")),
) -> UserOut:
    """Reset a user's password."""
    user = db.execute(select(User).where(User.id == user_id, User.org_id == current_user.org_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.hashed_password = get_password_hash(payload.new_password)
    db.add(user)
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="reset_password", resource_type="user", resource_id=str(user.id), details="Password reset")
    return UserOut.model_validate(user, from_attributes=True)
