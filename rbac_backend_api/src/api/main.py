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

from src.routers.auth import router as auth_router
from src.routers.organizations import router as organizations_router
from src.routers.users import router as users_router
from src.routers.roles import router as roles_router
from src.routers.permissions import router as permissions_router
from src.routers.audit_logs import router as audit_logs_router
from src.routers.init_data import router as init_router
from src.routers.health import router as health_router

# Basic logging configuration (can be overridden by deployment)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

openapi_tags = [
    {"name": "health", "description": "Health check and service info"},
    {"name": "auth", "description": "Authentication endpoints"},
    {"name": "rbac", "description": "RBAC management endpoints"},
]

app = FastAPI(
    title=os.getenv("PROJECT_NAME", "RBAC Backend API"),
    description="Multi-tenant RBAC backend with JWT auth and SQLAlchemy",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(users_router)
app.include_router(roles_router)
app.include_router(permissions_router)
app.include_router(audit_logs_router)
app.include_router(init_router)
app.include_router(health_router)

# PUBLIC_INTERFACE
@app.get("/", tags=["health"], summary="Health Check", description="Basic service health check.")
def health_check():
    """
    Basic liveness probe for the service.

    Returns:
        JSON object with a message indicating service status.
    """
    return {"message": "Healthy"}
