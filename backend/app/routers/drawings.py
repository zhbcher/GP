from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models.drawing import Drawing
from app.models.watchlist import Watchlist
from app.schemas import DrawingCreate, DrawingUpdate, DrawingRead
from fastapi import HTTPException

router = APIRouter(prefix="/api/drawings", tags=["drawings"])


def _serialize(d: Drawing) -> dict:
    return {
        "id": d.id, "stock_code": d.stock_code, "period": d.period,
        "type": d.type, "points": __import__("json").loads(d.points),
        "style": __import__("json").loads(d.style),
        "text_content": d.text_content, "visible": d.visible,
        "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
    }


@router.get("")
async def list_drawings(stock_code: str, period: str = "daily", db: AsyncSession = Depends(get_db)):
    q = select(Drawing).where(
        Drawing.stock_code == stock_code,
        Drawing.period == period,
    )
    result = await db.execute(q)
    return [_serialize(d) for d in result.scalars().all()]


@router.post("")
async def create_drawing(data: DrawingCreate, db: AsyncSession = Depends(get_db)):
    # Verify stock exists
    stock = await db.scalar(select(Watchlist).where(Watchlist.stock_code == data.stock_code))
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not in watchlist")

    # Idempotency check
    if data.idempotency_key:
        existing = await db.scalar(
            select(Drawing).where(Drawing.idempotency_key == data.idempotency_key)
        )
        if existing:
            return _serialize(existing)

    import json
    drawing = Drawing(
        stock_code=data.stock_code,
        period=data.period,
        type=data.type,
        points=json.dumps(data.points),
        style=json.dumps(data.style),
        text_content=data.text_content,
        idempotency_key=data.idempotency_key,
    )
    db.add(drawing)
    await db.commit()
    await db.refresh(drawing)
    return _serialize(drawing)


@router.put("/{did}")
async def update_drawing(did: int, data: DrawingUpdate, db: AsyncSession = Depends(get_db)):
    drawing = await db.get(Drawing, did)
    if not drawing:
        raise HTTPException(status_code=404, detail="Not found")

    import json
    patch = data.model_dump(exclude_unset=True)
    if "points" in patch:
        patch["points"] = json.dumps(patch["points"])
    if "style" in patch:
        patch["style"] = json.dumps(patch["style"])

    for k, v in patch.items():
        setattr(drawing, k, v)
    await db.commit()
    await db.refresh(drawing)
    return _serialize(drawing)


@router.delete("/{did}")
async def delete_drawing(did: int, db: AsyncSession = Depends(get_db)):
    drawing = await db.get(Drawing, did)
    if not drawing:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(drawing)
    await db.commit()
    return {"ok": True}
