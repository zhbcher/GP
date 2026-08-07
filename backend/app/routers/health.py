from fastapi import APIRouter

router = APIRouter()


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "data_sources": {"mootdx": "not_checked", "akshare": "not_checked"},
    }
