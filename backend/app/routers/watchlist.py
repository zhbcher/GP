from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.db import get_db
from app.data_sources.manager import manager as data_manager
from app.models.group import Group
from app.models.watchlist import Watchlist
from app.schemas import (
    GroupCreate, GroupUpdate, GroupRead,
    WatchlistCreate, WatchlistUpdate, WatchlistWithRealtime,
)
from app.services.realtime_service import get_realtime_quotes
from app.services.sync_service import sync_stock_kline

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


# ---- Groups ----

@router.get("/groups", response_model=list[GroupRead])
async def list_groups(db: AsyncSession = Depends(get_db)):
    q = select(Group).order_by(Group.sort_order, Group.id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/groups", response_model=GroupRead)
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db)):
    group = Group(**data.model_dump())
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.put("/groups/{gid}", response_model=GroupRead)
async def update_group(gid: int, data: GroupUpdate, db: AsyncSession = Depends(get_db)):
    group = await db.get(Group, gid)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(group, k, v)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/groups/{gid}")
async def delete_group(gid: int, db: AsyncSession = Depends(get_db)):
    group = await db.get(Group, gid)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    q = select(Watchlist).where(Watchlist.group_id == gid)
    result = await db.execute(q)
    for stock in result.scalars().all():
        stock.group_id = None
    await db.delete(group)
    await db.commit()
    return {"ok": True}


# ---- Watchlist ----

def _stock_dict(s: Watchlist, realtime=None) -> dict:
    return {
        "id": s.id,
        "stock_code": s.stock_code,
        "stock_name": s.stock_name,
        "group_id": s.group_id,
        "note": s.note,
        "sort_order": s.sort_order,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "realtime": realtime,
    }


@router.get("")
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    """SRS §4.3: grouped nested response {groups: [...], ungrouped: [...]}"""
    # Load groups
    gq = select(Group).order_by(Group.sort_order, Group.id)
    groups_result = await db.execute(gq)
    groups = groups_result.scalars().all()

    # Load all stocks
    sq = select(Watchlist).order_by(Watchlist.sort_order, Watchlist.id)
    stocks_result = await db.execute(sq)
    stocks = stocks_result.scalars().all()

    # Fetch realtime quotes
    codes = [s.stock_code for s in stocks]
    quotes = await get_realtime_quotes(codes) if codes else {}

    # Build grouped response
    grouped = []
    ungrouped = []
    stocks_by_group: dict[int, list] = {}
    for s in stocks:
        d = _stock_dict(s, quotes.get(s.stock_code))
        if s.group_id is not None:
            stocks_by_group.setdefault(s.group_id, []).append(d)
        else:
            ungrouped.append(d)

    for g in groups:
        grouped.append({
            "id": g.id,
            "name": g.name,
            "sort_order": g.sort_order,
            "stocks": stocks_by_group.get(g.id, []),
        })

    return {"groups": grouped, "ungrouped": ungrouped}


@router.post("")
async def add_watchlist(data: WatchlistCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(
        select(Watchlist).where(Watchlist.stock_code == data.stock_code)
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"{data.stock_code} already in watchlist")

    stock = Watchlist(**data.model_dump())
    db.add(stock)
    await db.commit()
    await db.refresh(stock)

    # SRS F-40: auto-sync K-line data on first add
    background_tasks.add_task(sync_stock_kline, data.stock_code)

    # SRS F-36: auto-create first annotation from note
    if data.note and data.note.strip():
        from app.models.annotation import Annotation
        import uuid
        annotation = Annotation(
            id=str(uuid.uuid4()),
            stock_code=data.stock_code,
            trade_date=datetime.now().strftime("%Y-%m-%d"),
            type="other",
            content=data.note.strip(),
            position="above",
        )
        db.add(annotation)
        await db.commit()

    return _stock_dict(stock)


@router.put("/{wid}")
async def update_watchlist(wid: int, data: WatchlistUpdate, db: AsyncSession = Depends(get_db)):
    stock = await db.get(Watchlist, wid)
    if not stock:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(stock, k, v)
    await db.commit()
    await db.refresh(stock)
    return _stock_dict(stock)


@router.delete("/{wid}")
async def delete_watchlist(wid: int, db: AsyncSession = Depends(get_db)):
    stock = await db.get(Watchlist, wid)
    if not stock:
        raise HTTPException(status_code=404, detail="Not found")
    # SRS F-24: delete from watchlist but keep annotations/drawings
    await db.delete(stock)
    await db.commit()
    return {"ok": True}


# ---- Batch Import ----

class ImportRequest(BaseModel):
    codes: list[str]


@router.post("/import")
async def import_watchlist(data: ImportRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Batch import stocks by code. Searches each code, adds matched stocks to watchlist."""
    imported = []
    skipped = []
    not_found = []

    # Load existing codes once
    existing_result = await db.execute(select(Watchlist.stock_code))
    existing_codes = {row[0] for row in existing_result.all()}

    for raw_code in data.codes:
        code = raw_code.strip()
        if not code:
            continue

        # Try to find the stock via search
        matched = None
        try:
            results = await data_manager.search_stocks(code, limit=10)
        except Exception:
            results = []

        if results:
            # Try exact match first, then suffix match
            for r in results:
                if r["code"].lower() == code.lower():
                    matched = r
                    break
            if not matched:
                # Try matching by suffix (e.g. input "600519" matches "sh600519")
                for r in results:
                    if r["code"].lower().endswith(code.lower()):
                        matched = r
                        break
            # If input has prefix and no exact/suffix match, take first result
            if not matched and len(results) == 1:
                matched = results[0]

        if not matched:
            not_found.append(code)
            continue

        full_code = matched["code"]
        stock_name = matched["name"]

        if full_code in existing_codes:
            skipped.append(code)
            continue

        # Add to watchlist
        stock = Watchlist(stock_code=full_code, stock_name=stock_name)
        db.add(stock)
        existing_codes.add(full_code)
        imported.append({"code": full_code, "name": stock_name})

        # Trigger K-line sync
        background_tasks.add_task(sync_stock_kline, full_code)

    await db.commit()
    return {"imported": imported, "skipped": skipped, "not_found": not_found}