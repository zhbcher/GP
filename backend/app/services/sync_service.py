"""
Data sync service.
Fetches K-line data from external sources and stores in DB.

Priority: mootdx → Baidu → Sina → Akshare (per a-stock-data skill)
mootdx unavailable overseas (TCP 7709 blocked), falls back to HTTP sources.
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
from app.data_sources.a_stock_data import get_daily_kline, is_regular_a_share, get_all_a_share_codes

logger = logging.getLogger(__name__)


async def _normalize_volume(volume: int) -> int:
    """Convert volume from shares (股) to lots (手).

    Sina/Baidu APIs return volume in shares. klinecharts expects lots (1 lot = 100 shares).
    Heuristic: if volume > 1_000_000, assume it's in shares and convert to lots.
    """
    if volume and volume > 1_000_000:
        return volume // 100
    return volume


async def validate_and_fix_volume(db: AsyncSession) -> dict:
    """Validate and fix volume data anomalies.
    
    Strategy: For records with volume < 100,000 (in lots), multiply by 100.
    This catches cases where volume was already in lots but got double-divided.
    """
    from sqlalchemy import update, select
    
    # Find anomalies
    result = await db.execute(
        select(KlineData.id, KlineData.volume)
        .where(
            KlineData.volume < 100_000,
            KlineData.volume > 0,
            KlineData.trade_date >= '2020-01-01'
        )
    )
    records = result.fetchall()
    
    if not records:
        return {"fixed": 0, "message": "No anomalies found"}
    
    fixed = 0
    for row_id, current_vol in records:
        corrected_vol = current_vol * 100
        await db.execute(
            update(KlineData)
            .where(KlineData.id == row_id)
            .values(volume=corrected_vol)
        )
        fixed += 1
    
    return {"fixed": fixed, "message": f"Fixed {fixed} records"}


async def sync_stock_kline(stock_code: str, days: int = 1000) -> dict:
    """Fetch and store K-line data for a stock. Returns sync result."""
    # Use a-stock-data priority routing (Sina → Baidu → Akshare)
    try:
        _, rows, source = await asyncio.to_thread(get_daily_kline, stock_code, None)
    except Exception as e:
        logger.error(f"Failed to fetch kline for {stock_code}: {e}")
        return {"stock_code": stock_code, "status": "error", "message": str(e)}

    if not rows:
        return {"stock_code": stock_code, "status": "empty", "message": "No data returned"}

    # Convert to DB format (rows already have trade_date from Sina/Baidu)
    # Normalize volume from shares to lots
    # NOTE: source row order varies — mootdx returns old→new, Sina/Baidu return new→old.
    # Sort ascending by trade_date, then take the LATEST `days` bars, so a small `days`
    # (e.g. 30 used by the 15:30 daily job) always updates the most recent data.
    rows_sorted = sorted(rows, key=lambda r: r.get("trade_date", ""))
    upserted = 0
    async with async_session_maker() as db:
        for r in rows_sorted[-days:]:
            stmt = (
                insert(KlineData)
                .values(
                    stock_code=stock_code,
                    trade_date=r["trade_date"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=await _normalize_volume(r["volume"]),
                    amount=r.get("amount", 0),
                )
                .prefix_with("OR REPLACE")
            )
            await db.execute(stmt)
            upserted += 1
        await db.commit()

    logger.info(f"Synced {upserted} bars for {stock_code} via {source}")
    
    # Data quality check
    async with async_session_maker() as db:
        fix_result = await validate_and_fix_volume(db)
        if fix_result["fixed"] > 0:
            logger.warning(f"Fixed {fix_result['fixed']} volume anomalies for {stock_code}")
    
    return {
        "stock_code": stock_code,
        "status": "ok",
        "bars": upserted,
        "source": source,
        "volume_fixes": fix_result.get("fixed", 0),
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


async def sync_all_stocks_daily(date_str: Optional[str] = None) -> dict:
    """Fetch today's daily K-line for ALL stocks in database.

    Uses a-stock-data priority routing: mootdx → Baidu → Sina → Akshare.
    Runs concurrently (MAX_CONCURRENCY at a time).
    
    Only syncs regular A-shares (not B-shares, ETFs, funds).
    """
    from app.models.kline_data import KlineData
    from sqlalchemy import select, distinct

    if date_str is None:
        from datetime import date as _date
        date_str = _date.today().isoformat()

    # Get all stock codes, filter to regular A-shares
    async with async_session_maker() as db:
        result = await db.execute(select(distinct(KlineData.stock_code)).order_by(KlineData.stock_code))
        all_codes = [row[0] for row in result.all()]
    
    # Filter to regular A-shares
    codes = [c for c in all_codes if is_regular_a_share(c)]
    
    logger.info(f"Filtered {len(all_codes)} codes to {len(codes)} regular A-shares")

    if not codes:
        logger.info("No regular A-share stocks in database")
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    MAX_CONCURRENCY = 30
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _sync_one(code: str) -> tuple[str, str]:
        """Fetch one stock's data for date_str. Returns (code, status)."""
        async with semaphore:
            try:
                _, rows, source = await asyncio.to_thread(get_daily_kline, code, date_str)
            except Exception as e:
                return code, f"error:{e}"

            if not rows:
                return code, "no_data"

            async with async_session_maker() as db:
                for r in rows:
                    stmt = (
                        insert(KlineData)
                        .values(
                            stock_code=code,
                            trade_date=r["trade_date"],
                            open=r["open"],
                            high=r["high"],
                            low=r["low"],
                            close=r["close"],
                            volume=await _normalize_volume(r["volume"]),
                            amount=r.get("amount", 0),
                        )
                        .prefix_with("OR REPLACE")
                    )
                    await db.execute(stmt)
                await db.commit()

            return code, f"ok({source})"

    # Run all
    tasks = [_sync_one(code) for code in codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if isinstance(r, tuple) and r[1].startswith("ok"))
    skipped = sum(1 for r in results if isinstance(r, tuple) and r[1] == "no_data")
    errors = [r for r in results if isinstance(r, tuple) and r[1].startswith("error:")]

    # Count sources
    source_counts = {}
    for r in results:
        if isinstance(r, tuple) and r[1].startswith("ok("):
            src = r[1].replace("ok(", "").replace(")", "")
            source_counts[src] = source_counts.get(src, 0) + 1

    logger.info(f"Daily sync complete: {success}/{len(codes)} OK {source_counts}, {skipped} skipped, {len(errors)} errors")
    if errors:
        logger.warning(f"Errors: {errors[:5]}")
    
    # Run data validation
    try:
        async with async_session_maker() as db:
            fix_result = await validate_and_fix_volume(db)
            logger.info(f"Volume validation: {fix_result['message']}")
    except Exception as e:
        logger.error(f"Volume validation failed: {e}")

    return {
        "total": len(codes),
        "success": success,
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors[:10],
        "date": date_str,
        "sources": source_counts,
        "volume_fixes": fix_result if 'fix_result' in locals() else {"fixed": 0},
    }


async def sync_full_a_share_market(date_str: Optional[str] = None) -> dict:
    """Fetch today's daily K-line for ALL A-shares from Sina.
    
    This is for initial population - fetches the complete A-share list from Sina,
    then syncs kline for each stock.
    """
    if date_str is None:
        from datetime import date as _date
        date_str = _date.today().isoformat()

    logger.info(f"Fetching full A-share list for {date_str}...")
    
    # Get all A-share codes from Sina
    all_codes = await asyncio.to_thread(get_all_a_share_codes)
    logger.info(f"Got {len(all_codes)} A-share codes from Sina")
    
    if not all_codes:
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0, "error": "No A-share codes fetched"}

    MAX_CONCURRENCY = 30
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def _sync_one(code: str) -> tuple[str, str]:
        """Fetch one stock's data for date_str. Returns (code, status)."""
        async with semaphore:
            try:
                _, rows, source = await asyncio.to_thread(get_daily_kline, code, date_str)
            except Exception as e:
                return code, f"error:{e}"

            if not rows:
                return code, "no_data"

            async with async_session_maker() as db:
                for r in rows:
                    stmt = (
                        insert(KlineData)
                        .values(
                            stock_code=code,
                            trade_date=r["trade_date"],
                            open=r["open"],
                            high=r["high"],
                            low=r["low"],
                            close=r["close"],
                            volume=await _normalize_volume(r["volume"]),
                            amount=r.get("amount", 0),
                        )
                        .prefix_with("OR REPLACE")
                    )
                    await db.execute(stmt)
                await db.commit()

            return code, f"ok({source})"

    # Run all
    tasks = [_sync_one(code) for code in all_codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if isinstance(r, tuple) and r[1].startswith("ok"))
    skipped = sum(1 for r in results if isinstance(r, tuple) and r[1] == "no_data")
    errors = [r for r in results if isinstance(r, tuple) and r[1].startswith("error:")]

    # Count sources
    source_counts = {}
    for r in results:
        if isinstance(r, tuple) and r[1].startswith("ok("):
            src = r[1].replace("ok(", "").replace(")", "")
            source_counts[src] = source_counts.get(src, 0) + 1

    logger.info(f"Full A-share sync complete: {success}/{len(all_codes)} OK {source_counts}, {skipped} skipped, {len(errors)} errors")
    if errors:
        logger.warning(f"Errors: {errors[:5]}")
    
    # Run data validation
    try:
        async with async_session_maker() as db:
            fix_result = await validate_and_fix_volume(db)
            logger.info(f"Volume validation: {fix_result['message']}")
    except Exception as e:
        logger.error(f"Volume validation failed: {e}")

    return {
        "total": len(all_codes),
        "success": success,
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors[:10],
        "date": date_str,
        "sources": source_counts,
        "volume_fixes": fix_result if 'fix_result' in locals() else {"fixed": 0},
    }


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
        raw_vol = int(float(parts[5]))
        # Eastmoney also returns shares, convert to lots
        rows.append({
            "trade_date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": raw_vol // 100 if raw_vol > 1_000_000 else raw_vol,
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
