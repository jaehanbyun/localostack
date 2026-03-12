from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


EXEMPT_PATHS = {
    ("POST", "/v3/auth/tokens"),
    ("GET", "/"),
    ("GET", "/v3"),
}

EXEMPT_PREFIXES_GET = ["/v3/auth/tokens"]


class KeystoneAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        method = request.method
        path = request.url.path.rstrip("/") or "/"

        if (method, path) in EXEMPT_PATHS:
            return await call_next(request)

        if method in ("GET", "HEAD", "DELETE") and path == "/v3/auth/tokens":
            pass  # these require auth, fall through
        elif method == "POST" and path == "/v3/auth/tokens":
            return await call_next(request)

        token_id = request.headers.get("X-Auth-Token")
        if not token_id:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Authentication required", "code": 401}},
            )

        store = getattr(request.app.state, "keystone_store", None)
        if store is None:
            return await call_next(request)

        token = store.validate_token(token_id)
        if token is None:
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Invalid or expired token", "code": 401}},
            )

        request.state.user_id = token.user_id
        request.state.project_id = token.project_id
        request.state.roles = token.roles

        return await call_next(request)
