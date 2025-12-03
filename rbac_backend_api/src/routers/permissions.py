from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.models.audit_log import AuditLog
from src.models.permission import Permission
from src.schemas.permission import PermissionCreate, PermissionOut
from src.security.dependencies import get_current_user, require_permission
from src.models.user import User

router = APIRouter(prefix="/api/permissions", tags=["rbac"])

# Use centralized DB dependency that handles 503 when DB is unavailable

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

class PermissionUpdate(BaseModel):
    """Payload to update permission."""
    name: Optional[str] = Field(None, description="Permission name")
    description: Optional[str] = Field(None, description="Permission description")

# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=PermissionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create permission",
    description="Create a permission within caller's org. Requires 'permissions:write' permission.",
)
def create_permission(
    payload: PermissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("permissions:write")),
) -> PermissionOut:
    """Create permission in caller's org."""
    if payload.org_id != current_user.org_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-organization operation not allowed")
    existing = db.execute(
        select(Permission).where(Permission.org_id == payload.org_id, Permission.name == payload.name)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission name already exists in org")

    perm = Permission(org_id=payload.org_id, name=payload.name, description=payload.description)
    db.add(perm)
    db.flush()
    _audit(db, org_id=perm.org_id, user_id=current_user.id, action="create", resource_type="permission", resource_id=str(perm.id), details=f"Created permission '{perm.name}'")
    return PermissionOut.model_validate(perm, from_attributes=True)

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[PermissionOut],
    summary="List permissions",
    description="List permissions in caller's org. Requires 'permissions:read' permission.",
)
def list_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("permissions:read")),
) -> List[PermissionOut]:
    """List org permissions."""
    rows = db.execute(select(Permission).where(Permission.org_id == current_user.org_id).order_by(Permission.id.desc())).scalars().all()
    return [PermissionOut.model_validate(p, from_attributes=True) for p in rows]

# PUBLIC_INTERFACE
@router.get(
    "/{permission_id}",
    response_model=PermissionOut,
    summary="Get permission",
    description="Get permission by id in caller's org. Requires 'permissions:read' permission.",
)
def get_permission(
    permission_id: int = Path(..., description="Permission ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("permissions:read")),
) -> PermissionOut:
    """Get permission."""
    perm = db.execute(select(Permission).where(Permission.id == permission_id, Permission.org_id == current_user.org_id)).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    return PermissionOut.model_validate(perm, from_attributes=True)

# PUBLIC_INTERFACE
@router.put(
    "/{permission_id}",
    response_model=PermissionOut,
    summary="Update permission",
    description="Update a permission in caller's org. Requires 'permissions:write' permission.",
)
def update_permission(
    updates: PermissionUpdate,
    permission_id: int = Path(..., description="Permission ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("permissions:write")),
) -> PermissionOut:
    """Update permission."""
    perm = db.execute(select(Permission).where(Permission.id == permission_id, Permission.org_id == current_user.org_id)).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    if updates.name is not None and updates.name != perm.name:
        existing = db.execute(
            select(Permission).where(Permission.org_id == current_user.org_id, Permission.name == updates.name, Permission.id != perm.id)
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Permission name already exists in org")
        perm.name = updates.name
    if updates.description is not None:
        perm.description = updates.description
    db.add(perm)
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="update", resource_type="permission", resource_id=str(perm.id), details="Updated permission fields")
    return PermissionOut.model_validate(perm, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{permission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete permission",
    description="Delete a permission in caller's org. Requires 'permissions:write' permission.",
)
def delete_permission(
    permission_id: int = Path(..., description="Permission ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("permissions:write")),
) -> None:
    """Delete permission."""
    perm = db.execute(select(Permission).where(Permission.id == permission_id, Permission.org_id == current_user.org_id)).scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission not found")
    db.execute(delete(Permission).where(Permission.id == permission_id))
    _audit(db, org_id=current_user.org_id, user_id=current_user.id, action="delete", resource_type="permission", resource_id=str(permission_id), details=f"Deleted permission '{perm.name}'")
    return None
