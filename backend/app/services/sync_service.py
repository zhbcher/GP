"""
Data sync service.
Fetches K-line data from external sources and stores in DB.
"""
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, delete
from app.db import async_session_maker
from app.models.kline_data import KlineData
from app.models.adjust_factor import AdjustFactor
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
