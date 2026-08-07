from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import date, datetime, timedelta
from pydantic import BaseModel
from app.db import get_db
from app.models.journal import Journal
from app.models.annotation import Annotation

router = APIRouter(prefix="/api/journal", tags=["journal"])


class JournalUpsert(BaseModel):
    trade_date: str
    operations: str = ""
    market_obs: str = ""
    plan: str = ""
    mood: str = "neutral"


def _serialize(j: Journal) -> dict:
    return {
        "id": j.id,
        "trade_date": j.trade_date.isoformat() if j.trade_date else None,
        "operations": j.operations,
        "market_obs": j.market_obs,
        "plan": j.plan,
        "mood": j.mood,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }


@router.get("")
async def get_journal(date: str = Query(..., description="YYYY-MM-DD"), db: AsyncSession = Depends(get_db)):
    """Get journal entry for a specific date."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    j = await db.scalar(select(Journal).where(Journal.trade_date == d))
    if not j:
        return {"trade_date": date, "operations": "", "market_obs": "", "plan": "", "mood": "neutral"}
    return _serialize(j)


@router.put("")
async def upsert_journal(data: JournalUpsert, db: AsyncSession = Depends(get_db)):
    """Create or update journal entry (upsert by trade_date)."""
    try:
        d = datetime.strptime(data.trade_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    j = await db.scalar(select(Journal).where(Journal.trade_date == d))
    if j:
        j.operations = data.operations
        j.market_obs = data.market_obs
        j.plan = data.plan
        j.mood = data.mood
        j.updated_at = datetime.utcnow()
    else:
        j = Journal(
            trade_date=d,
            operations=data.operations,
            market_obs=data.market_obs,
            plan=data.plan,
            mood=data.mood,
        )
        db.add(j)
    await db.commit()
    await db.refresh(j)
    return _serialize(j)


@router.get("/recent")
async def recent_journals(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """Get recent journal entries (summary list)."""
    cutoff = date.today() - timedelta(days=days)
    q = (
        select(Journal)
        .where(Journal.trade_date >= cutoff)
        .order_by(Journal.trade_date.desc())
    )
    result = await db.execute(q)
    journals = result.scalars().all()
    return [
        {
            "trade_date": j.trade_date.isoformat(),
            "mood": j.mood,
            "summary": (j.operations or "")[:80],
        }
        for j in journals
    ]


@router.get("/{date}/annotations")
async def date_annotations(date: str, db: AsyncSession = Depends(get_db)):
    """Get all annotations across stocks for a given date."""
    q = (
        select(Annotation)
        .where(Annotation.trade_date == date)
        .order_by(Annotation.stock_code)
    )
    result = await db.execute(q)
    annotations = result.scalars().all()
    return [
        {
            "id": a.id,
            "stock_code": a.stock_code,
            "trade_date": a.trade_date,
            "type": a.type,
            "content": a.content,
            "position": a.position,
        }
        for a in annotations
    ]
