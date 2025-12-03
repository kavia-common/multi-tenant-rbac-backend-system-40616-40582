from typing import Optional

from pydantic import BaseModel, Field


class Token(BaseModel):
    """JWT token pair or single token."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type, typically 'bearer'")


class TokenPayload(BaseModel):
    """Payload extracted from JWT."""
    sub: str = Field(..., description="Subject (user id)")
    org_id: int = Field(..., description="Organization ID")
    exp: Optional[int] = Field(None, description="Expiration timestamp (seconds since epoch)")
