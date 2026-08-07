"""
Data sync service.
Fetches K-line data from external sources and stores in DB.
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from app.db import async_session_maker
from app.models.kline_data import KlineData
from app.models.adjust_factor import AdjustFactor
from app.models.kline_adjusted import KlineAdjusted
from app.data_sources.manager import manager
from app.data_sources.mootdx_source import MootdxSource

logger = logging.getLogger(__name__)


async def sync_stock_kline(stock_code: str, days: int = 1000) -> dict:
    """Fetch and store K-line data for a stock. Returns sync result."""
    async with async_session_maker() as db:
        # Use mootdx directly (TCP, no proxy issues); fall back to manager
        try:
            mootdx_src = MootdxSource()
            raw_data = await mootdx_src.fetch_kline(stock_code, "daily")
        except Exception:
            try:
                raw_data = await manager.get_kline(stock_code, "daily")
            except Exception as e:
                logger.error(f"Failed to fetch kline for {stock_code}: {e}")
                return {"stock_code": stock_code, "status": "error", "message": str(e)}

        if not raw_data:
            return {"stock_code": stock_code, "status": "empty", "message": "No data returned"}

        # Sort by date ascending
        raw_data.sort(key=lambda x: x.get("timestamp", 0))

        # Take last N days
        raw_data = raw_data[-days:]

        upserted = 0
        for item in raw_data:
            trade_date = datetime.utcfromtimestamp(item["timestamp"] / 1000).strftime("%Y-%m-%d")

            stmt = (
                insert(KlineData)
                .values(
                    stock_code=stock_code,
                    trade_date=trade_date,
                    open=item["open"],
                    high=item["high"],
                    low=item["low"],
                    close=item["close"],
                    volume=item["volume"],
                    amount=item.get("turnover", 0),
                )
                .prefix_with("OR REPLACE")
            )
            await db.execute(stmt)
            upserted += 1

        await db.commit()

        # Sync adjust factors (use mootdx xdxr data, akshare/eastmoney API is unreliable)
        try:
            mootdx_src = MootdxSource()
            factors_raw = await mootdx_src.fetch_adjust_factors(stock_code)
            if factors_raw:
                for f in factors_raw:
                    stmt = (
                        insert(AdjustFactor)
                        .values(stock_code=stock_code, trade_date=f["trade_date"], factor=f["factor"])
                        .prefix_with("OR REPLACE")
                    )
                    await db.execute(stmt)
                await db.commit()
        except Exception as e:
            logger.warning(f"Adjust factor sync failed for {stock_code}: {e}")

        logger.info(f"Synced {upserted} bars for {stock_code}")
        return {
            "stock_code": stock_code,
            "status": "ok",
            "bars": upserted,
            "date_range": f"{raw_data[0].get('timestamp', 0)} - {raw_data[-1].get('timestamp', 0)}",
        }


async def sync_watchlist() -> dict:
    """Sync K-line data for all stocks in watchlist."""
    async with async_session_maker() as db:
        from app.models.watchlist import Watchlist
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    results = []
    for code in codes:
        result = await sync_stock_kline(code)
        results.append(result)

    return {"synced": len(results), "results": results}


def _to_ak_symbol(stock_code: str) -> str:
    """'sh600519' -> '600519' (akshare uses bare 6-digit codes)."""
    return stock_code[2:] if len(stock_code) == 8 else stock_code


def _fetch_akshare_hist(symbol: str, adjust: str) -> list[dict]:
    """Fetch full-history adjusted daily K-line from eastmoney.

    Eastmoney blocks Python TLS fingerprints (RemoteDisconnected), but system
    curl passes, so we shell out to curl and parse the JSON ourselves.
    """
    import json
    import subprocess

    market = "1" if symbol.startswith("6") else "0"
    fqt = "1" if adjust == "qfq" else "2"
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt={fqt}&secid={market}.{symbol}&beg=19900101&end=20500101"
        f"&ut=7eea3edcaed734bea9cbfc24409ed989"
    )
    out = subprocess.run(
        ["curl", "-s", "--max-time", "60", url],
        capture_output=True, timeout=90,
    )
    payload = json.loads(out.stdout.decode("utf-8", "replace"))
    klines = (payload.get("data") or {}).get("klines") or []
    rows = []
    for line in klines:
        parts = line.split(",")
        rows.append({
            "trade_date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": int(float(parts[5])),
            "amount": float(parts[6]),
        })
    return rows


async def sync_adjusted_kline(stock_code: str, adj_type: str) -> dict:
    """Fetch authoritative qfq/hfq daily K-line from akshare and cache in kline_adjusted.

    Full-history pull; safe to re-run (OR REPLACE upsert). ~1 request per stock.
    """
    if adj_type not in ("qfq", "hfq"):
        return {"stock_code": stock_code, "status": "error", "message": f"bad adj_type {adj_type}"}

    symbol = _to_ak_symbol(stock_code)
    loop = asyncio.get_event_loop()
    try:
        rows = await loop.run_in_executor(None, _fetch_akshare_hist, symbol, adj_type)
    except Exception as e:
        logger.error(f"akshare {adj_type} fetch failed for {stock_code}: {e}")
        return {"stock_code": stock_code, "status": "error", "message": str(e)}

    if not rows:
        return {"stock_code": stock_code, "status": "empty", "message": "akshare returned no data"}

    async with async_session_maker() as db:
        for r in rows:
            stmt = (
                insert(KlineAdjusted)
                .values(stock_code=stock_code, trade_date=r["trade_date"], adj_type=adj_type, **{
                    "open": r["open"], "high": r["high"], "low": r["low"],
                    "close": r["close"], "volume": r["volume"], "amount": r["amount"],
                })
                .prefix_with("OR REPLACE")
            )
            await db.execute(stmt)
        await db.commit()

    logger.info(f"Synced {len(rows)} {adj_type} bars for {stock_code}")
    return {"stock_code": stock_code, "status": "ok", "adj_type": adj_type, "bars": len(rows)}
