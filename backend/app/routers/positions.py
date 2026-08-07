"""Positions (holdings) router."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models.position import Position
from app.models.kline_data import KlineData
from app.schemas import PositionCreate, PositionUpdate, PositionRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("/summary")
async def positions_summary(db: AsyncSession = Depends(get_db)):
    """Grand total across ALL positions (all stocks).
    Price priority: realtime quote > latest kline close.
    """
    result = await db.execute(select(Position))
    positions = result.scalars().all()

    codes = list({p.stock_code for p in positions})
    prices: dict[str, float] = {}
    price_sources: dict[str, str] = {}

    # Latest close per stock from DB
    for code in codes:
        row = await db.execute(
            select(KlineData.close)
            .where(KlineData.stock_code == code)
            .order_by(KlineData.trade_date.desc())
            .limit(1)
        )
        close = row.scalar_one_or_none()
        prices[code] = close or 0.0
        price_sources[code] = "close"

    # Overlay realtime quotes when available
    if codes:
        try:
            from app.data_sources.mootdx_source import MootdxSource
            src = MootdxSource()
            quotes = await src.fetch_realtime(codes)
            for code, q in quotes.items():
                if q.get("price", 0) > 0:
                    prices[code] = q["price"]
                    price_sources[code] = "realtime"
        except Exception as e:
            logger.warning(f"Realtime quotes for summary failed: {e}")

    market_value = sum(prices.get(p.stock_code, 0.0) * p.quantity for p in positions)
    total_cost = sum(p.cost_price * p.quantity for p in positions)
    total_profit = market_value - total_cost
    profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0.0

    return {
        "market_value": round(market_value, 2),
        "total_cost": round(total_cost, 2),
        "total_profit": round(total_profit, 2),
        "profit_pct": round(profit_pct, 2),
        "position_count": len(positions),
        "stock_count": len(codes),
    }


@router.get("", response_model=list[PositionRead])
async def list_positions(stock_code: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Position).order_by(Position.created_at.desc())
    if stock_code:
        q = q.where(Position.stock_code == stock_code)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=PositionRead, status_code=201)
async def create_position(data: PositionCreate, db: AsyncSession = Depends(get_db)):
    pos = Position(
        stock_code=data.stock_code,
        stock_name=data.stock_name,
        cost_price=data.cost_price,
        quantity=data.quantity,
        buy_date=data.buy_date,
        note=data.note,
    )
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return pos


@router.put("/{pos_id}", response_model=PositionRead)
async def update_position(pos_id: int, data: PositionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Position).where(Position.id == pos_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(404, "Position not found")
    update_data = data.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(pos, k, v)
    await db.commit()
    await db.refresh(pos)
    return pos


@router.delete("/{pos_id}", status_code=204)
async def delete_position(pos_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Position).where(Position.id == pos_id))
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(404, "Position not found")
    await db.delete(pos)
    await db.commit()
