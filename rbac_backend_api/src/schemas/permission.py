from typing import Optional

from pydantic import BaseModel, Field


class PermissionCreate(BaseModel):
    """Payload to create a permission."""
    org_id: int = Field(..., description="Organization ID")
    name: str = Field(..., description="Permission name")
    description: Optional[str] = Field(None, description="Permission description")


class PermissionOut(BaseModel):
    """Permission response."""
    id: int = Field(..., description="Permission ID")
    org_id: int = Field(..., description="Organization ID")
    name: str = Field(..., description="Permission name")
    description: Optional[str] = Field(None, description="Permission description")

    class Config:
        from_attributes = True
