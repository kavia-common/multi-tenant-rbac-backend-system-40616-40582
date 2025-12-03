from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Payload to create a user."""
    org_id: int = Field(..., description="Organization ID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    password: str = Field(..., description="Plain text password")


class UserOut(BaseModel):
    """User response payload."""
    id: int = Field(..., description="User ID")
    org_id: int = Field(..., description="Organization ID")
    email: EmailStr = Field(..., description="User email")
    full_name: Optional[str] = Field(None, description="Full name")
    is_active: bool = Field(..., description="Is active")

    class Config:
        from_attributes = True
