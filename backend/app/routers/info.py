"""Info router: individual stock information endpoints."""
from fastapi import APIRouter, Query

from app.services import info_service

router = APIRouter(prefix="/api/info", tags=["info"])


@router.get("/{code}/overview")
async def stock_overview(code: str):
    """Aggregated overview: valuation + fund flow + concepts + lockup risk."""
    return await info_service.get_overview(code)


@router.get("/{code}/news")
async def stock_news(code: str, limit: int = Query(20, le=50)):
    """Individual stock news."""
    return await info_service.get_news(code, limit)


@router.get("/{code}/announcements")
async def stock_announcements(code: str, limit: int = Query(30, le=100)):
    """Announcements from cninfo."""
    return await info_service.get_announcements(code, limit)


@router.get("/{code}/reports")
async def stock_reports(code: str, limit: int = Query(10, le=30)):
    """Research reports + EPS forecast."""
    return await info_service.get_reports(code, limit)


@router.get("/{code}/finance")
async def stock_finance(code: str):
    """Core financial indicators + dividends."""
    return await info_service.get_finance(code)


@router.get("/{code}/profile")
async def stock_profile(code: str):
    """F10 profile + holder count changes."""
    return await info_service.get_profile(code)
