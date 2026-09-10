"""HTTP origin and optional API-token enforcement."""

from __future__ import annotations

import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


API_TOKEN_HEADER = "X-ResearchMate-Token"


class ApiSecurityMiddleware(BaseHTTPMiddleware):
    """Reject untrusted browser origins and enforce a configured API token."""

    def __init__(self, app, *, allowed_origins: tuple[str, ...], api_token: str):
        super().__init__(app)
        self.allowed_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)
        self.api_token = api_token

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in self.allowed_origins:
            return JSONResponse(
                {"detail": "Origin is not allowed"},
                status_code=403,
            )

        # CORS preflight carries no application credentials; the CORS
        # middleware validates it and the real request is authenticated later.
        if request.method == "OPTIONS":
            return await call_next(request)

        if self.api_token and request.url.path != "/api/health":
            supplied = request.headers.get(API_TOKEN_HEADER, "")
            if not supplied or not secrets.compare_digest(supplied, self.api_token):
                return JSONResponse(
                    {"detail": "Valid API token required"},
                    status_code=401,
                    headers={"WWW-Authenticate": "ApiKey"},
                )

        return await call_next(request)
