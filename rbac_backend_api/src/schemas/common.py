from pydantic import BaseModel, Field


class Message(BaseModel):
    """Simple message schema for responses."""
    message: str = Field(..., description="Message text")
