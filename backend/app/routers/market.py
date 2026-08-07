"""Market router: market sentiment endpoints."""
from fastapi import APIRouter, Query

from app.services import info_service

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/limit-up")
async def limit_up():
    """Limit-up pool + sentiment stats."""
    return await info_service.get_limit_up()


@router.get("/north-flow")
async def north_flow():
    """Northbound capital flow (realtime)."""
    return await info_service.get_north_flow()


@router.get("/dragon-tiger")
async def dragon_tiger(date: str | None = Query(None)):
    """Daily dragon-tiger board. date format: YYYY-MM-DD, defaults to today."""
    return await info_service.get_dragon_tiger(date)


@router.get("/sectors")
async def sectors():
    """Industry ranking + board fund flow."""
    return await info_service.get_sectors()


@router.get("/hot-rank")
async def hot_rank():
    """Hot rank from THS + EastMoney."""
    return await info_service.get_hot_rank()
