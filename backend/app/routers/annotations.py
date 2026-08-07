from fastapi import APIRouter, Depends, Query, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db import get_db
from app.models.annotation import Annotation
from app.models.watchlist import Watchlist
from app.models.kline_data import KlineData
from app.schemas import AnnotationCreate, AnnotationUpdate, AnnotationRead, AnnotationDisplayUpdate
from fastapi import HTTPException
import uuid
import csv
import io
from datetime import datetime, date, timedelta
from collections import defaultdict

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


def _serialize(a: Annotation) -> dict:
    return {
        "id": a.id, "stock_code": a.stock_code, "trade_date": a.trade_date,
        "type": a.type, "content": a.content, "position": a.position,
        "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(),
    }


@router.get("")
async def list_annotations(stock_code: str, db: AsyncSession = Depends(get_db)):
    q = select(Annotation).where(Annotation.stock_code == stock_code).order_by(Annotation.trade_date)
    result = await db.execute(q)
    return [_serialize(a) for a in result.scalars().all()]


@router.post("")
async def create_annotation(data: AnnotationCreate, db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    # Verify stock exists
    stock = await db.scalar(select(Watchlist).where(Watchlist.stock_code == data.stock_code))
    if not stock:
        raise HTTPException(status_code=404, detail="Stock not in watchlist")

    # Idempotency check
    key = idempotency_key or data.idempotency_key
    if key:
        existing = await db.scalar(
            select(Annotation).where(Annotation.idempotency_key == key)
        )
        if existing:
            return _serialize(existing)

    dump = data.model_dump(exclude={"idempotency_key"})
    annotation = Annotation(
        id=str(uuid.uuid4()),
        idempotency_key=key,
        **dump,
    )
    db.add(annotation)
    await db.commit()
    await db.refresh(annotation)
    return _serialize(annotation)


@router.put("/{aid}")
async def update_annotation(aid: str, data: AnnotationUpdate, db: AsyncSession = Depends(get_db)):
    annotation = await db.get(Annotation, aid)
    if not annotation:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(annotation, k, v)
    annotation.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(annotation)
    return _serialize(annotation)


@router.delete("/{aid}")
async def delete_annotation(aid: str, db: AsyncSession = Depends(get_db)):
    annotation = await db.get(Annotation, aid)
    if not annotation:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(annotation)
    await db.commit()
    return {"ok": True}


@router.delete("")
async def batch_delete(stock_code: str, db: AsyncSession = Depends(get_db)):
    q = select(Annotation).where(Annotation.stock_code == stock_code)
    result = await db.execute(q)
    annotations = result.scalars().all()
    count = 0
    for a in annotations:
        await db.delete(a)
        count += 1
    await db.commit()
    return {"deleted": count}


@router.patch("/display")
async def toggle_display(data: AnnotationDisplayUpdate, db: AsyncSession = Depends(get_db)):
    # This just returns info; actual visibility is managed client-side via overlay
    # The endpoint confirms the action and could persist display preferences in future
    from fastapi import Response
    q = select(Annotation).where(Annotation.stock_code == data.stock_code)
    if data.type:
        q = q.where(Annotation.type == data.type)
    result = await db.execute(q)
    count = len(result.scalars().all())
    return {"stock_code": data.stock_code, "visible": data.visible, "affected_count": count}


@router.get("/export")
async def export_annotations(stock_code: str, format: str = Query("md", pattern="^(md|csv)$"), db: AsyncSession = Depends(get_db)):
    q = select(Annotation).where(Annotation.stock_code == stock_code).order_by(Annotation.trade_date)
    result = await db.execute(q)
    annotations = result.scalars().all()

    if not annotations:
        return Response(content="No annotations found", media_type="text/plain")

    # Fetch kline data for close price and change calculation
    dates = [a.trade_date for a in annotations]
    kline_q = select(KlineData).where(
        KlineData.stock_code == stock_code,
        KlineData.trade_date.in_(dates),
    )
    kline_result = await db.execute(kline_q)
    kline_map = {k.trade_date: k for k in kline_result.scalars().all()}

    # Also fetch previous day close for change calculation
    all_kline_q = select(KlineData).where(
        KlineData.stock_code == stock_code,
    ).order_by(KlineData.trade_date)
    all_kline_result = await db.execute(all_kline_q)
    all_klines = all_kline_result.scalars().all()
    prev_close_map = {}
    for i, k in enumerate(all_klines):
        if i > 0:
            prev_close_map[k.trade_date] = all_klines[i - 1].close

    if format == "md":
        lines = [f"# {stock_code} 交易标注\n",
                 "| 日期 | 类型 | 内容 | 当日收盘 | 当日涨跌 |",
                 "|------|------|------|---------|---------|"]
        for a in annotations:
            kline = kline_map.get(a.trade_date)
            close_str = f"{kline.close:.2f}" if kline else "-"
            change_str = "-"
            if kline and a.trade_date in prev_close_map:
                prev = prev_close_map[a.trade_date]
                if prev > 0:
                    change_pct = (kline.close - prev) / prev * 100
                    change_str = f"{change_pct:+.2f}%"
            lines.append(f"| {a.trade_date} | {a.type} | {a.content} | {close_str} | {change_str} |")
        content = "\n".join(lines) + "\n"
        media_type = "text/markdown"
    else:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["日期", "类型", "内容", "当日收盘", "当日涨跌", "创建时间"])
        for a in annotations:
            kline = kline_map.get(a.trade_date)
            close_str = f"{kline.close:.2f}" if kline else ""
            change_str = ""
            if kline and a.trade_date in prev_close_map:
                prev = prev_close_map[a.trade_date]
                if prev > 0:
                    change_pct = (kline.close - prev) / prev * 100
                    change_str = f"{change_pct:+.2f}%"
            writer.writerow([a.trade_date, a.type, a.content, close_str, change_str, a.created_at.isoformat()])
        content = output.getvalue()
        media_type = "text/csv; charset=utf-8"

    from fastapi import Response as FastAPIResponse
    return FastAPIResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{stock_code}_annotations.{format}"'},
    )


@router.get("/timeline")
async def get_timeline(days: int = Query(30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """Return all annotations across stocks from the last N days, grouped by trade_date desc."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    q = (
        select(Annotation, Watchlist.stock_name)
        .outerjoin(Watchlist, Annotation.stock_code == Watchlist.stock_code)
        .where(Annotation.trade_date >= cutoff)
        .order_by(Annotation.trade_date.desc(), Annotation.created_at.desc())
    )
    result = await db.execute(q)
    rows = result.all()

    grouped: dict[str, list] = defaultdict(list)
    for ann, stock_name in rows:
        grouped[ann.trade_date].append({
            "id": ann.id,
            "stock_code": ann.stock_code,
            "stock_name": stock_name or "",
            "type": ann.type,
            "content": ann.content,
            "trade_date": ann.trade_date,
        })

    timeline = [
        {"date": d, "annotations": grouped[d]}
        for d in sorted(grouped.keys(), reverse=True)
    ]
    return {"timeline": timeline}


@router.get("/trade-pairs")
async def get_trade_pairs(stock_code: str, db: AsyncSession = Depends(get_db)):
    """Match buy/sell annotations FIFO and calculate trade statistics."""
    # Fetch all buy and sell annotations sorted by trade_date
    q = (
        select(Annotation)
        .where(Annotation.stock_code == stock_code)
        .where(Annotation.type.in_(["buy", "sell"]))
        .order_by(Annotation.trade_date)
    )
    result = await db.execute(q)
    annos = result.scalars().all()

    if not annos:
        return {"pairs": [], "summary": {"total_trades": 0, "win_count": 0, "loss_count": 0, "avg_return_pct": 0.0, "win_rate": 0.0}}

    # Collect all dates for kline price lookup
    all_dates = [a.trade_date for a in annos]
    kline_q = (
        select(KlineData)
        .where(KlineData.stock_code == stock_code)
        .where(KlineData.trade_date.in_(all_dates))
    )
    kline_result = await db.execute(kline_q)
    kline_map = {k.trade_date: k.close for k in kline_result.scalars().all()}

    # FIFO matching: each buy matches the next unmatched sell after it
    pairs = []
    sell_used = [False] * len(annos)

    for i, ann in enumerate(annos):
        if ann.type != "buy":
            continue
        # Find the next unmatched sell after this buy
        matched_sell = None
        for j in range(i + 1, len(annos)):
            if annos[j].type == "sell" and not sell_used[j]:
                sell_used[j] = True
                matched_sell = annos[j]
                break

        buy_price = kline_map.get(ann.trade_date)
        if matched_sell:
            sell_price = kline_map.get(matched_sell.trade_date)
            if buy_price and sell_price and buy_price > 0:
                return_pct = round((sell_price - buy_price) / buy_price * 100, 2)
                d1 = date.fromisoformat(ann.trade_date)
                d2 = date.fromisoformat(matched_sell.trade_date)
                holding_days = (d2 - d1).days
                annual_pct = round(return_pct / holding_days * 365, 2) if holding_days > 0 else 0.0
            else:
                return_pct = None
                sell_price = kline_map.get(matched_sell.trade_date) if matched_sell else None
                holding_days = None
                annual_pct = None
            pairs.append({
                "buy_date": ann.trade_date,
                "buy_price": buy_price,
                "buy_content": ann.content,
                "sell_date": matched_sell.trade_date,
                "sell_price": sell_price,
                "sell_content": matched_sell.content,
                "return_pct": return_pct,
                "holding_days": holding_days,
                "annual_pct": annual_pct,
                "status": "closed",
            })
        else:
            # Unmatched buy — still holding
            pairs.append({
                "buy_date": ann.trade_date,
                "buy_price": buy_price,
                "buy_content": ann.content,
                "sell_date": None,
                "sell_price": None,
                "sell_content": None,
                "return_pct": None,
                "holding_days": None,
                "annual_pct": None,
                "status": "open",
            })

    # Compute summary (only closed trades with known return)
    closed = [p for p in pairs if p["status"] == "closed" and p["return_pct"] is not None]
    total_trades = len(closed)
    win_count = sum(1 for p in closed if p["return_pct"] > 0)
    loss_count = sum(1 for p in closed if p["return_pct"] <= 0)
    avg_return_pct = round(sum(p["return_pct"] for p in closed) / total_trades, 2) if total_trades > 0 else 0.0
    win_rate = round(win_count / total_trades * 100, 1) if total_trades > 0 else 0.0

    return {
        "pairs": pairs,
        "summary": {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "avg_return_pct": avg_return_pct,
            "win_rate": win_rate,
        },
    }
