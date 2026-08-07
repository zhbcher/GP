"""News router: industry news endpoints (sector × date layout)."""
from fastapi import APIRouter

from app.services import news_service_v2 as news_service

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("/sectors")
async def list_sectors():
    """All sectors with item counts."""
    sectors = await news_service.get_sectors()
    return {"sectors": sectors, "refreshing": news_service.is_refreshing()}


@router.get("/sector/{sector}/days")
async def sector_days(sector: str):
    """Last 7 days with counts for a sector."""
    days = await news_service.get_sector_days(sector)
    return {"sector": sector, "days": days}


@router.get("/sector/{sector}/day/{date}")
async def sector_day(sector: str, date: str):
    """News items + digest for a sector+date."""
    return await news_service.get_sector_day(sector, date)


@router.post("/refresh")
async def refresh_news():
    """Trigger async news refresh."""
    if news_service.is_refreshing():
        return {"ok": False, "message": "Refresh already in progress"}
    news_service.trigger_refresh()
    return {"ok": True, "message": "Refresh started"}
