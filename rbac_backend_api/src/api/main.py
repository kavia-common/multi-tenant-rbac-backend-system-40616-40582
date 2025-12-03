"""
FastAPI application entrypoint.

- Registers all routers (auth, RBAC, audit, init, health).
- Keeps database checks lazy so the app can start without a DB connection.
- OpenAPI includes tags and a root health endpoint for liveness checks.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import sys
from pathlib import Path


openapi_tags = [
    {"name": "health", "description": "Health check and service info"},
    {"name": "auth", "description": "Authentication endpoints"},
    {"name": "rbac", "description": "RBAC management endpoints"},
]


# Ensure 'src' is on sys.path for absolute imports when running with different working directories
_src_dir = Path(__file__).resolve().parents[1]
if str(_src_dir) not in sys.path:
    # Prepend so our project src takes precedence without affecting other global paths
    sys.path.insert(0, str(_src_dir))

# PUBLIC_INTERFACE
def create_app() -> FastAPI:
    """Create and configure the FastAPI application without triggering side effects at import time.

    This function wires up all routers using lazy imports to avoid touching the database at module import.
    Returns:
        FastAPI: Configured FastAPI application.
    """
    # Basic logging configuration (can be overridden by deployment)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    app = FastAPI(
        title=os.getenv("PROJECT_NAME", "RBAC Backend API"),
        description="Multi-tenant RBAC backend with JWT auth and SQLAlchemy",
        version="0.1.0",
        openapi_tags=openapi_tags,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Lazy imports to avoid import-time DB access or heavy side-effects.
    # Try absolute import path first, and fall back to relative package import to be resilient in different runners.
    try:
        from src.routers.health import router as health_router  # type: ignore
        from src.routers.auth import router as auth_router  # type: ignore
        from src.routers.users import router as users_router  # type: ignore
        from src.routers.roles import router as roles_router  # type: ignore
        from src.routers.permissions import router as permissions_router  # type: ignore
        from src.routers.organizations import router as organizations_router  # type: ignore
        from src.routers.audit_logs import router as audit_logs_router  # type: ignore
        from src.routers.init_data import router as init_router  # type: ignore
    except ModuleNotFoundError:
        # Fallback for environments that resolve module paths differently
        from ..routers.health import router as health_router  # type: ignore
        from ..routers.auth import router as auth_router  # type: ignore
        from ..routers.users import router as users_router  # type: ignore
        from ..routers.roles import router as roles_router  # type: ignore
        from ..routers.permissions import router as permissions_router  # type: ignore
        from ..routers.organizations import router as organizations_router  # type: ignore
        from ..routers.audit_logs import router as audit_logs_router  # type: ignore
        from ..routers.init_data import router as init_router  # type: ignore

    # Register routers (respect prefixes defined in each router file)
    app.include_router(health_router, tags=["health"])
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(users_router, prefix="/api", tags=["rbac"])
    app.include_router(roles_router, prefix="/api", tags=["rbac"])
    app.include_router(permissions_router, prefix="/api", tags=["rbac"])
    app.include_router(organizations_router, prefix="/api", tags=["rbac"])
    app.include_router(audit_logs_router, prefix="/api", tags=["rbac"])
    app.include_router(init_router, prefix="/api", tags=["health"])

    @app.get("/", tags=["health"], summary="Health Check", description="Basic service health check.")
    # PUBLIC_INTERFACE
    def health_check():
        """Service liveness probe endpoint.

        Returns:
            dict: simple status payload.
        """
        return {"status": "ok"}

    return app


# FastAPI expects a module-level `app` for uvicorn import path usage (src.api.main:app)
app = create_app()
