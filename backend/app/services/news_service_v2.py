"""News service v2: reads from investment-news data.js (file-based).

Pipeline: investment-news/run_all.sh → data.js → this service → GP frontend.
"""
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DATA_JS = "/Users/zhoubo/GP/investment-news/data.js"
RUN_SCRIPT = "/Users/zhoubo/GP/investment-news/run_all.sh"
_BJT = timezone(timedelta(hours=8))

_cache: dict = {"data": None, "mtime": 0}
_refreshing = False


def _load_data() -> dict:
    """Load and cache data.js (reload when file changes)."""
    global _cache
    try:
        mtime = os.path.getmtime(DATA_JS)
        if _cache["data"] is not None and mtime == _cache["mtime"]:
            return _cache["data"]
        txt = open(DATA_JS, encoding="utf-8").read()
        data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
        _cache = {"data": data, "mtime": mtime}
        return data
    except Exception as e:
        logger.warning(f"Failed to load data.js: {e}")
        return _cache["data"] or {"industries": []}


def _ts_to_date(ts: int) -> str:
    """Unix timestamp → YYYY-MM-DD in Beijing time."""
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=_BJT).strftime("%Y-%m-%d")


def _ts_to_time(ts: int) -> str:
    """Unix timestamp → HH:MM in Beijing time."""
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=_BJT).strftime("%H:%M")


# ── Query API (sector × date) ────────────────────────────────────────────

async def get_sectors() -> list[dict]:
    """All sectors with item counts."""
    data = _load_data()
    result = []
    for ind in data.get("industries", []):
        result.append({"sector": ind["key"], "count": len(ind.get("items", []))})
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


async def get_sector_days(sector: str) -> list[dict]:
    """Last 7 days with counts for a sector."""
    data = _load_data()
    today = datetime.now(_BJT)

    # Find the industry
    ind = None
    for i in data.get("industries", []):
        if i["key"] == sector:
            ind = i
            break
    if not ind:
        return []

    # Group items by date
    by_date: dict[str, int] = {}
    for item in ind.get("items", []):
        d = _ts_to_date(item.get("ts", 0))
        if d:
            by_date[d] = by_date.get(d, 0) + 1

    # Build 7-day list
    days = []
    for i in range(7):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        count = by_date.get(d, 0)
        has_digest = bool(ind.get("points")) and i == 0  # digest only for today
        days.append({"date": d, "count": count, "has_digest": has_digest})
    return days


async def get_sector_day(sector: str, date_str: str) -> dict:
    """News items + digest for a sector+date."""
    data = _load_data()

    ind = None
    for i in data.get("industries", []):
        if i["key"] == sector:
            ind = i
            break
    if not ind:
        return {"sector": sector, "date": date_str, "digest": [], "items": []}

    # Digest (points) — only for the most recent day with data
    digest = []
    today = datetime.now(_BJT).strftime("%Y-%m-%d")
    if date_str == today and ind.get("points"):
        digest = [p.get("t", "") for p in ind["points"] if p.get("t")]

    # Filter items by date
    items = []
    for idx, item in enumerate(ind.get("items", [])):
        d = _ts_to_date(item.get("ts", 0))
        if d != date_str:
            continue
        items.append({
            "id": idx,
            "sector": sector,
            "title": item.get("title", ""),
            "title_zh": item.get("zh", ""),
            "link": item.get("url", ""),
            "date": item.get("time", ""),
            "summary": item.get("summary", ""),
            "content": item.get("content", ""),
            "content_zh": item.get("content_zh", ""),
            "source": item.get("source", ""),
        })

    return {"sector": sector, "date": date_str, "digest": digest, "items": items}


# ── Refresh ──────────────────────────────────────────────────────────────

def is_refreshing() -> bool:
    return _refreshing


def trigger_refresh():
    """Fire-and-forget: run the full pipeline script."""
    global _refreshing
    if _refreshing:
        return
    _refreshing = True

    import asyncio

    async def _run():
        global _refreshing
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/bash", RUN_SCRIPT,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info("[news] Pipeline refresh complete")
                # Invalidate cache
                _cache["mtime"] = 0
            else:
                logger.warning(f"[news] Pipeline failed: {(stderr or b'').decode()[-300:]}")
        except Exception as e:
            logger.warning(f"[news] Pipeline error: {e}")
        finally:
            _refreshing = False

    asyncio.create_task(_run())


async def load_news_on_startup():
    """Verify data.js exists and log stats."""
    data = _load_data()
    total = sum(len(ind.get("items", [])) for ind in data.get("industries", []))
    sectors = len(data.get("industries", []))
    if total:
        logger.info(f"News data.js: {total} items across {sectors} sectors")
