"""
Routers package initialization.

Ensures `src.routers` can be imported. Routers are individually defined in their modules.
"""
__all__ = [
    "auth",
    "organizations",
    "users",
    "roles",
    "permissions",
    "audit_logs",
    "init_data",
    "health",
]
