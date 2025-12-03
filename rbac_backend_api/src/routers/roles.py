from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.audit_log import AuditLog
from src.models.role import Role
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.schemas.role import RoleCreate, RoleOut
from src.security.dependencies import get_current_user, require_permission
from src.models.user import User

router = APIRouter(prefix="/api/roles", tags=["rbac"])

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

class RoleUpdate(BaseModel):
    """Payload to update role."""
    name: Optional[str] = Field(None, description="Role name")
    description: Optional[str] = Field(None, description="Role description")

# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=RoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create role",
    description="Create a role within caller's org. Requires 'roles:write' permission.",
)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:write")),
) -> RoleOut:
    """Create role in caller's org."""
    if payload.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization operation not allowed")

    existing = db.execute(
        select(Role).where(Role.org_id == payload.org_id, Role.name == payload.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name already exists in org")

    role = Role(org_id=payload.org_id, name=payload.name, description=payload.description)
    db.add(role)
    db.flush()
    _audit(db, org_id=role.org_id, user_id=current_user.id, action="create", resource_type="role", resource_id=str(role.id), details=f"Created role '{role.name}'")
    return RoleOut.model_validate(role, from_attributes=True)

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[RoleOut],
    summary="List roles",
    description="List roles in caller's org. Requires 'roles:read' permission.",
)
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:read")),
) -> List[RoleOut]:
    """List roles in caller's org."""
    rows = db.execute(select(Role).where(Role.org_id == current_user.org_id).order_by(Role.id.desc())).scalars().all()
    return [RoleOut.model_validate(r, from_attributes=True) for r in rows]

# PUBLIC_INTERFACE
@router.get(
    "/{role_id}",
    response_model=RoleOut,
    summary="Get role",
    description="Get role by id in caller's org. Requires 'roles:read' permission.",
)
def get_role(
    role_id: int = Path(..., description="Role ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:read")),
) -> RoleOut:
    """Get role in caller's org."""
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return RoleOut.model_validate(role, from_attributes=True)

# PUBLIC_INTERFACE
@router.put(
    "/{role_id}",
    response_model=RoleOut,
    summary="Update role",
    description="Update a role in caller's org. Requires 'roles:write' permission.",
)
def update_role(
    updates: RoleUpdate,
    role_id: int = Path(..., description="Role ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:write")),
) -> RoleOut:
    """Update role (name/description)."""
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if updates.name is not None and updates.name != role.name:
        # check uniqueness
        existing = db.execute(
            select(Role).where(Role.org_id == current_user.org_id, Role.name == updates.name, Role.id != role.id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role name already exists in org")
        role.name = updates.name
    if updates.description is not None:
        role.description = updates.description
    db.add(role)
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="update", resource_type="role", resource_id=str(role.id), details="Updated role fields")
    return RoleOut.model_validate(role, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete role",
    description="Delete a role in caller's org. Requires 'roles:write' permission.",
)
def delete_role(
    role_id: int = Path(..., description="Role ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:write")),
) -> None:
    """Delete role in caller's org."""
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    db.execute(delete(Role).where(Role.id == role.id))
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="delete", resource_type="role", resource_id=str(role.id), details=f"Deleted role '{role.name}'")
    return None

# PUBLIC_INTERFACE
@router.post(
    "/{role_id}/permissions/{permission_id}",
    response_model=RoleOut,
    summary="Assign permission to role",
    description="Assign a permission to a role inside caller's org. Requires 'roles:write' permission.",
)
def assign_permission_to_role(
    role_id: int = Path(..., description="Role ID"),
    permission_id: int = Path(..., description="Permission ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:write")),
) -> RoleOut:
    """Assign permission to role ensuring org scoping."""
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    perm = db.execute(select(Permission).where(Permission.id == permission_id, Permission.org_id == current_user.org_id)).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    existing = db.execute(
        select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id)
    ).scalar_one_or_none()
    if not existing:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))
        _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="assign_permission", resource_type="role", resource_id=str(role.id), details=f"Assigned permission '{perm.name}'")
    return RoleOut.model_validate(role, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{role_id}/permissions/{permission_id}",
    response_model=RoleOut,
    summary="Remove permission from role",
    description="Remove a permission from a role in caller's org. Requires 'roles:write' permission.",
)
def remove_permission_from_role(
    role_id: int = Path(..., description="Role ID"),
    permission_id: int = Path(..., description="Permission ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("roles:write")),
) -> RoleOut:
    """Remove permission link."""
    role = db.execute(select(Role).where(Role.id == role_id, Role.org_id == current_user.org_id)).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    perm = db.execute(select(Permission).where(Permission.id == permission_id, Permission.org_id == current_user.org_id)).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id))
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="remove_permission", resource_type="role", resource_id=str(role.id), details=f"Removed permission '{perm.name}'")
    return RoleOut.model_validate(role, from_attributes=True)
