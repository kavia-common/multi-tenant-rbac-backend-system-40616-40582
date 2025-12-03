"""
Authentication helpers: password hashing and JWT encode/decode.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# PUBLIC_INTERFACE
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# PUBLIC_INTERFACE
def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


# PUBLIC_INTERFACE
def create_access_token(subject: str, org_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token for a user and org."""
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt.access_token_expire_minutes)
    expire = datetime.now(tz=timezone.utc) + expires_delta
    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "org_id": org_id,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.jwt.secret_key, algorithm=settings.jwt.algorithm)


# PUBLIC_INTERFACE
def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token, returning payload."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt.secret_key, algorithms=[settings.jwt.algorithm])
        return payload
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
