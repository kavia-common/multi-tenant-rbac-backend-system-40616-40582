from typing import Optional

from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    """Payload to create a role."""
    org_id: int = Field(..., description="Organization ID")
    name: str = Field(..., description="Role name")
    description: Optional[str] = Field(None, description="Role description")


class RoleOut(BaseModel):
    """Role response."""
    id: int = Field(..., description="Role ID")
    org_id: int = Field(..., description="Organization ID")
    name: str = Field(..., description="Role name")
    description: Optional[str] = Field(None, description="Role description")

    class Config:
        from_attributes = True
