"""Lightweight access-key auth for public deployment protection.

Usage: configure AUTH_KEY in .env, then access via URL ?key=***
The key is static (never expires, survives restarts).
"""
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import get_settings

settings = get_settings()


def verify_key(key: str) -> bool:
    """Constant-time comparison of provided key against configured AUTH_KEY."""
    if not settings.auth_key:
        return True  # no key configured = open access
    return secrets.compare_digest(key, settings.auth_key)


def extract_key(request: Request) -> str | None:
    """Extract access key from Authorization header or query param."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.query_params.get("key") or request.query_params.get("token")


async def auth_middleware_handler(request: Request, call_next):
    """Global middleware: protect /api/* except health and auth-check."""
    if not settings.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)

    # Public paths
    if path.startswith(("/api/health", "/api/auth/")):
        return await call_next(request)

    # OPTIONS preflight: bypass auth so CORS headers get through
    if request.method == "OPTIONS":
        return await call_next(request)

    key = extract_key(request)
    if not key or not verify_key(key):
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing access key"})

    return await call_next(request)


def verify_ws_key(key: str) -> bool:
    """Verify key for WebSocket connections."""
    if not settings.auth_key:
        return True
    return secrets.compare_digest(key, settings.auth_key)
