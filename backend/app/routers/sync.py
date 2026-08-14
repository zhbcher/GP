from fastapi import APIRouter, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import async_session_maker
from app.services.sync_service import sync_stock_kline, sync_watchlist, sync_all_stocks_daily

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


@router.post("/daily/all-stocks")
async def sync_daily_all_stocks(background_tasks: BackgroundTasks, date_str: str | None = None):
    """Fetch today's daily K-line for ALL stocks in database via eastmoney HTTP.
    
    Runs asynchronously — returns immediately with status.
    """
    background_tasks.add_task(sync_all_stocks_daily, date_str=date_str)
    return {"status": "queued", "date": date_str or "today"}


@router.get("/daily/status")
async def daily_sync_status():
    """Check when the last full market sync completed."""
    from app.db import async_session_maker
    from app.models.kline_data import KlineData
    from sqlalchemy import select, func
    
    async with async_session_maker() as db:
        r = await db.execute(select(func.max(KlineData.trade_date)))
        latest_date = r.scalar()
    
    from datetime import date as _date
    today = _date.today().isoformat()
    
    if latest_date == today:
        return {"status": "up_to_date", "latest_date": latest_date, "today": today}
    else:
        return {"status": "needs_sync", "latest_date": latest_date, "today": today}
