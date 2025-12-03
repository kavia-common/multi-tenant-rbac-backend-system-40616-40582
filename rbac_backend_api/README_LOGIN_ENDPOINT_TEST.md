# Login Endpoint Path Test Note

Purpose:
Ensure the authentication login endpoint is mounted at /api/auth/login (without duplicated segments).

What changed:
- The auth router now uses prefix="/auth".
- The main app includes the auth router with include_router(..., prefix="/api/auth").
- Combined, the login route resolves to /api/auth/login.

How to verify locally:
1) Start the FastAPI app and open the API docs:
   - Navigate to /docs and look for the POST /api/auth/login operation under "auth" tag.

2) cURL check:
   curl -s -o /dev/null -w "%{http_code}\n" \
     -H "Content-Type: application/json" \
     -d '{"org_id":1,"email":"someone@example.com","password":"secret"}' \
     http://localhost:3001/api/auth/login

   Expect a 401 (if credentials are wrong) or 200 with a token (if valid), but NOT a 404.

3) OpenAPI path check:
   - GET /openapi.json and confirm that there is a path entry for "/api/auth/login"
   - Ensure there is no "/api/auth/api/auth/login" entry.

Notes:
If you see duplicated segments in other routes, ensure only one of:
- The router itself has a full "/api/..." prefix, OR
- The include_router call specifies the "/api" prefix.
Do not set both to avoid duplication.
