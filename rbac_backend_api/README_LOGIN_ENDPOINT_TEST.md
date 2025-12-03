# Auth Route Path Verification

This project mounts routers to avoid duplicated prefixes. Final expected paths:

- POST /api/auth/login
- GET /api/auth/me
- GET /api/health/db
- RBAC resources under /api (e.g., /api/users, /api/roles, /api/permissions, /api/orgs, /api/audit_logs)

Quick tests (adjust HOST accordingly):

curl -sS -X POST "$HOST/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"org_id":1,"email":"test@example.com","password":"password"}'

# After obtaining a token:
TOKEN="Bearer <access_token_here>"
curl -sS -H "Authorization: $TOKEN" "$HOST/api/auth/me"

OpenAPI should show:
- POST /api/auth/login
- GET  /api/auth/me
- Other endpoints under /api/* (without duplicated /api segments)

Notes:
- DB/session access remains lazy and occurs only within request handlers via Depends(get_db).
- If you still see duplicated segments, ensure:
  - src/routers/auth.py defines APIRouter with no prefix
  - src/api/main.py includes auth router exactly once:
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
