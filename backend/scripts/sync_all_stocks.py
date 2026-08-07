"""批量同步所有自选股的全量历史 K 线数据。

mootdx 日 K 频率=9，单次最多 800 根，通过 start 偏移分页。
_fetch_bars 内部已经实现了分页，默认 count=5000，最大可设 8000+。

用法:
    cd ~/GP/backend && source .venv/bin/activate && python scripts/sync_all_stocks.py

逻辑:
    1. 从 watchlist 表读取所有自选股 stock_code
    2. 对每只股票，从 mootdx 分页拉取全量日 K（约 8000 根）
    3. 写入 kline_data 表（INSERT OR REPLACE / upsert）
    4. 输出每只股票拉取的行数及新增行数
"""
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db import async_session_maker
from app.data_sources.mootdx_source import MootdxSource

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# 日 K 频率码
FREQ_DAILY = 9
# mootdx 单次最多 800 根，分页步长
PAGE = 800
# 目标：每只股票拉取 6000 根（约 2000-2026 约 6300 个交易日）
MAX_BARS = 6000


def _fetch_all_bars(source: MootdxSource, code: str) -> list[dict]:
    """直接调用 mootdx 分页拉取全量日 K，返回统一格式的列表。

    _fetch_bars 默认 count=5000，但 2000 年至今约 6300 根。
    这里绕过 count 限制，手动分页直到拉完或达到 MAX_BARS。
    """
    client = source._get_client()
    pure_code = code[2:]  # strip sh/sz prefix

    all_rows = []
    seen = set()
    start = 0

    while len(all_rows) < MAX_BARS:
        df = client.bars(symbol=pure_code, frequency=FREQ_DAILY, start=start, offset=PAGE)
        if df is None or (hasattr(df, "empty") and df.empty):
            logger.info(f"    {code}: mootdx 返回空数据，已到历史起点")
            break

        new_count = 0
        for _, row in df.iterrows():
            dt = row.get("datetime")
            if dt is None:
                continue
            key = str(dt)
            if key in seen:
                continue
            seen.add(key)

            # 从 datetime 对象提取 trade_date
            if hasattr(dt, "strftime"):
                trade_date = dt.strftime("%Y-%m-%d")
            else:
                trade_date = str(dt)[:10]

            all_rows.append({
                "trade_date": trade_date,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row.get("vol", 0)),
                "amount": float(row.get("amount", 0)),
            })
            new_count += 1

        if new_count == 0:
            logger.info(f"    {code}: 无新数据，已到历史起点")
            break

        start += PAGE
        logger.info(f"    {code}: 已拉取 {len(all_rows)} 根 (start={start})")

    # 按日期升序排列
    all_rows.sort(key=lambda x: x["trade_date"])
    return all_rows


async def sync_all():
    source = MootdxSource()

    # 1. 从 watchlist 读取所有自选股
    async with async_session_maker() as db:
        result = await db.execute(
            text("SELECT DISTINCT stock_code FROM watchlist ORDER BY stock_code")
        )
        codes = [r[0] for r in result.fetchall()]

    logger.info(f"找到 {len(codes)} 只自选股")
    for c in codes:
        logger.info(f"  {c}")

    total_bars = 0
    total_inserted = 0

    for code in codes:
        try:
            logger.info(f"--- 开始同步 {code} ---")

            # 2. 分页拉取全量日 K
            bars = _fetch_all_bars(source, code)
            if not bars:
                logger.warning(f"  {code}: 无数据，跳过")
                continue

            logger.info(f"  {code}: mootdx 返回 {len(bars)} 根")

            # 3. 写入数据库 (INSERT OR REPLACE 批量 upsert)
            inserted = 0
            async with async_session_maker() as db:
                for bar in bars:
                    # SQLite 的 INSERT OR REPLACE 利用 idx_kline_code_date 唯一索引
                    await db.execute(
                        text("""
                            INSERT OR REPLACE INTO kline_data
                                (stock_code, trade_date, open, high, low, close, volume, amount)
                            VALUES
                                (:code, :date, :open, :high, :low, :close, :volume, :amount)
                        """),
                        {
                            "code": code,
                            "date": bar["trade_date"],
                            "open": bar["open"],
                            "high": bar["high"],
                            "low": bar["low"],
                            "close": bar["close"],
                            "volume": bar["volume"],
                            "amount": bar["amount"],
                        },
                    )
                    inserted += 1
                await db.commit()

            total_bars += len(bars)
            total_inserted += inserted
            logger.info(f"  ✓ {code}: {len(bars)} 根 (写入 {inserted})")

        except Exception as e:
            logger.error(f"  ✗ {code}: 失败 - {e}", exc_info=True)

    logger.info(f"=== 同步完成 ===")
    logger.info(f"总 K 线数: {total_bars}")
    logger.info(f"总写入数: {total_inserted}")


if __name__ == "__main__":
    asyncio.run(sync_all())