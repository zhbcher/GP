from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.db import get_db
from app.models.kline_data import KlineData
from app.models.adjust_factor import AdjustFactor
from app.models.watchlist import Watchlist
from app.schemas import KlineDataRead, KlineResponse
from app.services.kline_service import compute_adjusted, aggregate_period
from app.data_sources.mootdx_source import MootdxSource


MINUTE_PERIODS = {"5min", "15min", "30min", "60min"}

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/{code}/kline", response_model=KlineResponse)
async def get_kline(
    code: str,
    period: str = "daily",
    adjust: str = "qfq",
    limit: int = 2500,
    db: AsyncSession = Depends(get_db),
):
    # For non-daily periods, fetch all data first, aggregate, then apply limit
    # For daily, apply limit directly in SQL for efficiency
    # Minute K-line: fetch live from mootdx, skip DB entirely
    if period in MINUTE_PERIODS:
        stock_name = code
        wl = await db.scalar(select(Watchlist).where(Watchlist.stock_code == code))
        if wl:
            stock_name = wl.stock_name

        try:
            src = MootdxSource()
            data = await src.fetch_minute_kline(code, period, count=min(limit, 800))
            return KlineResponse(
                code=code, name=stock_name, period=period, adjust="none",
                data=[KlineDataRead(**d) for d in data], count=len(data),
            )
        except Exception as e:
            return KlineResponse(
                code=code, name=stock_name, period=period, adjust="none",
                data=[], count=0,
            )

    if period == "daily":
        q = (
            select(KlineData)
            .where(KlineData.stock_code == code)
            .order_by(KlineData.trade_date)
            .limit(limit)
        )
    else:
        q = (
            select(KlineData)
            .where(KlineData.stock_code == code)
            .order_by(KlineData.trade_date)
        )
    
    result = await db.execute(q)
    rows = result.scalars().all()

    if not rows:
        return KlineResponse(code=code, name=code, period=period, adjust=adjust, data=[], count=0)

    # Look up stock name from watchlist
    stock_name = code
    wl = await db.scalar(select(Watchlist).where(Watchlist.stock_code == code))
    if wl:
        stock_name = wl.stock_name

    data = [
        KlineDataRead(
            timestamp=int(datetime.strptime(row.trade_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000),
            open=row.open, high=row.high, low=row.low, close=row.close,
            volume=row.volume, turnover=row.amount,
        )
        for row in rows
    ]

    # Fetch adjust factors if needed
    factors = {}
    if adjust in ("qfq", "hfq"):
        dates = [r.trade_date for r in rows]
        q2 = select(AdjustFactor).where(
            AdjustFactor.stock_code == code,
            AdjustFactor.trade_date.in_(dates),
        )
        res2 = await db.execute(q2)
        for f in res2.scalars().all():
            factors[f.trade_date] = f.factor

    if factors:
        data = compute_adjusted(data, factors, adjust)

    if period != "daily":
        data = aggregate_period(data, period)
        # Apply limit after aggregation
        data = data[-limit:]

    return KlineResponse(
        code=code, name=stock_name, period=period, adjust=adjust,
        data=data, count=len(data),
    )


@router.get("/{code}/minute")
async def get_minute(code: str, db: AsyncSession = Depends(get_db)):
    """Get today's intraday minute data (240 points) for the stock.
    Not persisted — fetched live from mootdx each time.
    """
    # Look up stock name
    stock_name = code
    wl = await db.scalar(select(Watchlist).where(Watchlist.stock_code == code))
    if wl:
        stock_name = wl.stock_name

    try:
        src = MootdxSource()
        result = await src.fetch_minute(code)
        return {
            "code": code,
            "name": stock_name,
            "prev_close": result["prev_close"],
            "data": result["data"],
            "count": len(result["data"]),
        }
    except Exception as e:
        return {
            "code": code,
            "name": stock_name,
            "prev_close": 0,
            "data": [],
            "count": 0,
            "error": str(e),
        }


@router.get("/{code}/timeline")
async def get_timeline(code: str, db: AsyncSession = Depends(get_db)):
    """Get today's intraday timeline data for the stock.
    Alias for /minute — returns {code, data: [{time, price, avg_price, volume}], prev_close}.
    """
    stock_name = code
    wl = await db.scalar(select(Watchlist).where(Watchlist.stock_code == code))
    if wl:
        stock_name = wl.stock_name

    try:
        src = MootdxSource()
        result = await src.fetch_minute(code)
        return {
            "code": code,
            "name": stock_name,
            "prev_close": result["prev_close"],
            "data": result["data"],
            "count": len(result["data"]),
        }
    except Exception as e:
        return {
            "code": code,
            "name": stock_name,
            "prev_close": 0,
            "data": [],
            "count": 0,
            "error": str(e),
        }
