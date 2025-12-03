from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import os

from src.core.config import get_settings
from src.routers.auth import router as auth_router
from src.routers.organizations import router as organizations_router
from src.routers.users import router as users_router
from src.routers.roles import router as roles_router
from src.routers.permissions import router as permissions_router
from src.routers.audit_logs import router as audit_logs_router

# Basic logging configuration (can be overridden by deployment)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()

openapi_tags = [
    {"name": "health", "description": "Health check and service info"},
    {"name": "auth", "description": "Authentication endpoints"},
    {"name": "rbac", "description": "RBAC management endpoints"},
]

app = FastAPI(
    title=settings.project_name,
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


@app.get("/", tags=["health"], summary="Health Check", description="Basic service health check.")
def health_check():
    return {"message": "Healthy"}
