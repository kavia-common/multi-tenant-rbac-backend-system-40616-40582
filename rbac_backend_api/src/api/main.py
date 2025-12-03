from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.routers.auth import router as auth_router

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


@app.get("/", tags=["health"], summary="Health Check", description="Basic service health check.")
def health_check():
    return {"message": "Healthy"}
