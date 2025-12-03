from typing import Optional
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])

class DBHealth(BaseModel):
    """Database health status."""
    status: str = Field(..., description="Database status: ok | degraded | down")
    dsn: Optional[str] = Field(None, description="Connection context with password masked")
    notes: Optional[str] = Field(None, description="Additional information")


# PUBLIC_INTERFACE
@router.get(
    "/db",
    response_model=DBHealth,
    summary="Database health",
    description="Reports database health without causing startup failure. If DSN is missing, returns status 'degraded'.",
)
def health_db() -> DBHealth:
    """
    Inspect configuration to report DB health:
    - If no DSN is configured, return degraded (service can run without DB).
    - If DSN is configured, we don't force a live connection here; operational endpoints will probe when used.
    """
    settings = get_settings()
    dsn = settings.sql_alchemy_dsn
    if dsn:
        try:
            masked = f"mysql+pymysql://****:****@{dsn.split('@')[-1]}"
        except Exception:
            masked = "configured"
        return DBHealth(status="ok", dsn=masked, notes="DSN configured; connectivity probed on first DB use.")
    else:
        return DBHealth(status="degraded", dsn=None, notes="No DSN configured. Configure DB_DSN or MYSQL_* envs.")
