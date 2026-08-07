from fastapi import APIRouter, Query
from app.data_sources.manager import manager

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    results = await manager.search_stocks(q, limit)
    return results