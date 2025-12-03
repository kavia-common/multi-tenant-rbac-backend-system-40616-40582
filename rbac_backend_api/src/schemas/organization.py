from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    """Payload to create an organization."""
    name: str = Field(..., description="Organization name")


class OrganizationOut(BaseModel):
    """Organization response."""
    id: int = Field(..., description="Organization ID")
    name: str = Field(..., description="Organization name")

    class Config:
        from_attributes = True
