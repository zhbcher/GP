"""NV-003: Export/Import drawings and annotations as JSON for backup and migration."""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.drawing import Drawing
from app.models.annotation import Annotation
from app.models.watchlist import Watchlist

router = APIRouter(prefix="/api", tags=["data-io"])


def _serialize_drawing(d: Drawing) -> dict:
    return {
        "id": d.id,
        "stock_code": d.stock_code,
        "period": d.period,
        "type": d.type,
        "points": json.loads(d.points) if d.points else [],
        "style": json.loads(d.style) if d.style else {},
        "text_content": d.text_content,
        "visible": d.visible,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


def _serialize_annotation(a: Annotation) -> dict:
    return {
        "id": a.id,
        "stock_code": a.stock_code,
        "trade_date": a.trade_date,
        "type": a.type,
        "content": a.content,
        "position": a.position,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


@router.get("/export")
async def export_stock_data(stock_code: str, db: AsyncSession = Depends(get_db)):
    """Export drawings + annotations for a single stock as JSON."""
    # Get stock name from watchlist
    stock = await db.scalar(select(Watchlist).where(Watchlist.stock_code == stock_code))
    stock_name = stock.stock_name if stock else ""

    # Drawings
    d_result = await db.execute(select(Drawing).where(Drawing.stock_code == stock_code))
    drawings = [_serialize_drawing(d) for d in d_result.scalars().all()]

    # Annotations
    a_result = await db.execute(
        select(Annotation).where(Annotation.stock_code == stock_code).order_by(Annotation.trade_date)
    )
    annotations = [_serialize_annotation(a) for a in a_result.scalars().all()]

    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "drawings": drawings,
        "annotations": annotations,
    }


@router.get("/export/all")
async def export_all_data(db: AsyncSession = Depends(get_db)):
    """Export drawings + annotations for all stocks as JSON."""
    # All drawings
    d_result = await db.execute(select(Drawing))
    drawings = [_serialize_drawing(d) for d in d_result.scalars().all()]

    # All annotations
    a_result = await db.execute(select(Annotation).order_by(Annotation.stock_code, Annotation.trade_date))
    annotations = [_serialize_annotation(a) for a in a_result.scalars().all()]

    # Build stock list from watchlist for names
    w_result = await db.execute(select(Watchlist))
    stock_map = {w.stock_code: w.stock_name for w in w_result.scalars().all()}

    stocks = []
    for code in sorted(set(d["stock_code"] for d in drawings) | set(a["stock_code"] for a in annotations)):
        stocks.append({"stock_code": code, "stock_name": stock_map.get(code, "")})

    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "stocks": stocks,
        "drawings": drawings,
        "annotations": annotations,
    }


@router.post("/import")
async def import_data(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Import drawings + annotations from a JSON file. Skips duplicates."""
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    imported_drawings = 0
    imported_annotations = 0
    skipped = 0

    # ---- Import drawings ----
    for d in data.get("drawings", []):
        stock_code = d.get("stock_code")
        dtype = d.get("type", "")
        points = d.get("points", [])
        points_str = json.dumps(points)

        # Dedup by stock_code + type + points
        existing = await db.scalar(
            select(Drawing).where(
                Drawing.stock_code == stock_code,
                Drawing.type == dtype,
                Drawing.points == points_str,
            )
        )
        if existing:
            skipped += 1
            continue

        drawing = Drawing(
            stock_code=stock_code,
            period=d.get("period", "daily"),
            type=dtype,
            points=points_str,
            style=json.dumps(d.get("style", {})),
            text_content=d.get("text_content"),
            visible=d.get("visible", True),
        )
        db.add(drawing)
        imported_drawings += 1

    # ---- Import annotations ----
    for a in data.get("annotations", []):
        stock_code = a.get("stock_code")
        trade_date = a.get("trade_date", "")
        content = a.get("content", "")

        # Dedup by stock_code + trade_date + content
        existing = await db.scalar(
            select(Annotation).where(
                Annotation.stock_code == stock_code,
                Annotation.trade_date == trade_date,
                Annotation.content == content,
            )
        )
        if existing:
            skipped += 1
            continue

        import uuid
        annotation = Annotation(
            id=str(uuid.uuid4()),
            stock_code=stock_code,
            trade_date=trade_date,
            type=a.get("type", "watch"),
            content=content,
            position=a.get("position", "above"),
        )
        db.add(annotation)
        imported_annotations += 1

    await db.commit()

    return {
        "imported_drawings": imported_drawings,
        "imported_annotations": imported_annotations,
        "skipped": skipped,
    }
