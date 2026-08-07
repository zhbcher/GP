"""Backfill missing daily kline (raw/unadjusted) from Tencent fqkline API."""
import asyncio, sqlite3, sys
import httpx

DB = "/Users/zhoubo/GP/data/stock.db"
CODES = ["sh600519", "sh000858", "sh600339"]


async def fetch_raw_day(client, code, num=30):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,{num},"
    r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
    j = r.json()
    d = j["data"][code]
    bars = d.get("day") or d.get("qfqday") or []
    # [date, open, close, high, low, volume]
    return bars


async def main():
    conn = sqlite3.connect(DB)
    async with httpx.AsyncClient(timeout=15) as client:
        for code in CODES:
            bars = await fetch_raw_day(client, code)
            n = 0
            for b in bars:
                date, o, c, h, l, v = b[0], float(b[1]), float(b[2]), float(b[3]), float(b[4]), int(float(b[5]))
                conn.execute(
                    "INSERT OR REPLACE INTO kline_data (stock_code, trade_date, open, high, low, close, volume, amount) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (code, date, o, h, l, c, v, 0),
                )
                n += 1
            conn.commit()
            print(f"{code}: upserted {n} bars, last={bars[-1][0] if bars else 'none'}")
    conn.close()


asyncio.run(main())
