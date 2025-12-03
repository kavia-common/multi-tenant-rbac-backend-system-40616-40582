from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.db.session import SessionLocal
from src.models.audit_log import AuditLog
from src.models.organization import Organization
from src.schemas.organization import OrganizationCreate, OrganizationOut
from src.security.dependencies import get_current_user, require_role
from src.models.user import User

router = APIRouter(prefix="/api/orgs", tags=["rbac"])

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

# PUBLIC_INTERFACE
@router.post(
    "",
    response_model=OrganizationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization",
    description="Create a new organization (tenant). Requires the 'admin' role on caller's org to manage tenants.",
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> OrganizationOut:
    """Create an organization. This is a global action; we still log against the caller's org."""
    # Ensure unique name
    existing = db.execute(select(Organization).where(Organization.name == payload.name)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name already exists")
    org = Organization(name=payload.name)
    db.add(org)
    db.flush()  # get id
    # For creation, we don't yet know a 'target' org id separate from current user's org context; log with newly created org_id and resource
    _audit(db, org_id=org.id, user_id=None, action="create", resource_type="organization", resource_id=str(org.id), details=f"Created org '{org.name}'")
    return OrganizationOut.model_validate(org, from_attributes=True)

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[OrganizationOut],
    summary="List organizations",
    description="List organizations (tenant list). Requires 'admin' role.",
)
def list_organizations(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> List[OrganizationOut]:
    """List organizations. Restricted to admins."""
    rows = db.execute(select(Organization).order_by(Organization.id.desc())).scalars().all()
    return [OrganizationOut.model_validate(o, from_attributes=True) for o in rows]

# PUBLIC_INTERFACE
@router.get(
    "/{org_id}",
    response_model=OrganizationOut,
    summary="Get organization",
    description="Fetch a single organization by id. Requires 'admin' role.",
)
def get_organization(
    org_id: int = Path(..., description="Organization ID"),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> OrganizationOut:
    """Get organization by id."""
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationOut.model_validate(org, from_attributes=True)

# PUBLIC_INTERFACE
@router.put(
    "/{org_id}",
    response_model=OrganizationOut,
    summary="Update organization",
    description="Update organization name. Requires 'admin' role.",
)
def update_organization(
    payload: OrganizationCreate,
    org_id: int = Path(..., description="Organization ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_role("admin")),
) -> OrganizationOut:
    """Update organization by id."""
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # name unique check
    existing = db.execute(
        select(Organization).where(Organization.name == payload.name, Organization.id != org_id)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization name already exists")

    org.name = payload.name
    db.add(org)
    _audit(db, org_id=org.id, user_id=current_user.id, action="update", resource_type="organization", resource_id=str(org.id), details=f"Renamed to '{org.name}'")
    return OrganizationOut.model_validate(org, from_attributes=True)

# PUBLIC_INTERFACE
@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete organization",
    description="Delete an organization by id. Requires 'admin' role.",
)
def delete_organization(
    org_id: int = Path(..., description="Organization ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_role("admin")),
) -> None:
    """Delete organization."""
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    db.execute(delete(Organization).where(Organization.id == org_id))
    _audit(db, org_id=org_id, user_id=current_user.id, action="delete", resource_type="organization", resource_id=str(org_id), details="Organization deleted")
    return None
