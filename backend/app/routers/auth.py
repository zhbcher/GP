"""Auth router: key verification endpoint."""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import verify_key
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()


class VerifyRequest(BaseModel):
    key: str


@router.post("/verify")
async def verify(data: VerifyRequest):
    """Verify access key. Returns ok if valid."""
    if not settings.auth_enabled:
        return {"ok": True}
    if not verify_key(data.key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access key")
    return {"ok": True}


@router.get("/check")
async def check():
    """Check if auth is enabled (for frontend to decide whether to show key entry)."""
    return {"auth_enabled": settings.auth_enabled}
