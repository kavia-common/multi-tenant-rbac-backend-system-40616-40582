from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from src.db.session import get_db
from src.models.audit_log import AuditLog
from src.models.user import User
from src.security.dependencies import get_current_user, require_permission

router = APIRouter(prefix="/api/audit_logs", tags=["rbac"])

# Use centralized DB dependency that handles 503 when DB is unavailable

class AuditLogOut(BaseModel):
    """Audit log response model."""
    id: int = Field(..., description="Audit log ID")
    org_id: int = Field(..., description="Organization ID")
    user_id: Optional[int] = Field(None, description="User ID who performed the action")
    action: str = Field(..., description="Action name")
    resource_type: Optional[str] = Field(None, description="Resource type")
    resource_id: Optional[str] = Field(None, description="Resource ID")
    details: Optional[str] = Field(None, description="Details")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True

# PUBLIC_INTERFACE
@router.get(
    "",
    response_model=List[AuditLogOut],
    summary="List audit logs",
    description="List audit logs for caller's organization. Requires 'audit:read' permission.",
)
def list_audit_logs(
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("audit:read")),
) -> List[AuditLogOut]:
    """List audit logs with optional filters, restricted to caller's org."""
    conditions = [AuditLog.org_id == current_user.org_id]
    if action:
        conditions.append(AuditLog.action == action)
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)

    stmt = select(AuditLog).where(and_(*conditions)).order_by(AuditLog.id.desc())
    rows = db.execute(stmt).scalars().all()
    return [AuditLogOut.model_validate(a, from_attributes=True) for a in rows]
