from fastapi import APIRouter, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import async_session_maker
from app.services.sync_service import sync_stock_kline, sync_watchlist

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/kline/{stock_code}")
async def sync_kline(background_tasks: BackgroundTasks, stock_code: str, days: int = 1000):
    """Trigger K-line data sync for a stock (runs in background)."""
    background_tasks.add_task(sync_stock_kline, stock_code, days)
    return {"status": "queued", "stock_code": stock_code}


@router.post("/watchlist")
async def sync_all_watchlist(background_tasks: BackgroundTasks):
    """Sync K-line data for all watchlist stocks."""
    background_tasks.add_task(sync_watchlist)
    return {"status": "queued"}
