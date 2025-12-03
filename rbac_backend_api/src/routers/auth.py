from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.db.session import SessionLocal
from src.models.user import User
from src.schemas.auth import Token
from src.schemas.user import UserOut
from src.security.auth import create_access_token, verify_password
from src.security.dependencies import get_current_user

router = APIRouter(prefix="/api", tags=["auth"])


def get_db():
    """Yield a SQLAlchemy session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginRequest(BaseModel):
    """Login request payload."""
    org_id: int = Field(..., description="Organization ID to scope authentication")
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")


# PUBLIC_INTERFACE
@router.post(
    "/auth/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Login to obtain JWT access token",
    description="Authenticate with organization ID, email, and password to receive a JWT bearer token.",
    responses={
        200: {"description": "Successful login returns access token"},
        400: {"description": "Bad request"},
        401: {"description": "Invalid credentials"},
    },
)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> Token:
    """Authenticate a user by org_id and email, verify password, and issue a JWT access token."""
    stmt = select(User).where(User.org_id == request.org_id, User.email == request.email)
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    settings = get_settings()
    expires = timedelta(minutes=settings.jwt.access_token_expire_minutes)
    token = create_access_token(subject=str(user.id), org_id=user.org_id, expires_delta=expires)
    return Token(access_token=token, token_type="bearer")


# PUBLIC_INTERFACE
@router.get(
    "/me",
    response_model=UserOut,
    summary="Get current authenticated user",
    description="Return profile details of the current authenticated user based on the bearer token.",
    responses={
        200: {"description": "Current user details"},
        401: {"description": "Unauthorized"},
    },
)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the current authenticated user's profile."""
    return UserOut.model_validate(current_user, from_attributes=True)
