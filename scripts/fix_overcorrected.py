#!/usr/bin/env python3
"""
Fix rows where volume was divided by 100 too many times.
Detection: amount = volume * 100 * close exactly (ratio ≈ 1.0000)
AND volume < 100,000 (too small for a real A-share daily volume).
These are rows where vol and amt were both divided by 100 extra.

Fix: volume *= 100, amount *= 100 (restore correct units).
"""
import sqlite3, logging, os, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    # Find all rows: ratio == 1.0000 exactly AND volume < 100000
    # These are computed values, not real data.
    cur.execute("""
        SELECT stock_code, trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE amount > 0 AND volume > 0 AND close > 0
          AND volume < 100000
          AND ABS(amount/(volume*100.0*close) - 1.0) < 0.0001
    """)
    rows = cur.fetchall()
    log.info(f"Found {len(rows):,} rows with volume < 100K and ratio ≈ 1.0000")

    # Group by stock
    from collections import defaultdict
    by_stock = defaultdict(int)
    for r in rows:
        by_stock[r[0]] += 1

    log.info(f"Affected stocks: {len(by_stock)}")
    for code, cnt in sorted(by_stock.items(), key=lambda x: -x[1])[:15]:
        log.info(f"  {code}: {cnt:,} rows")

    if '--dry-run' in sys.argv:
        log.info("DRY RUN, no changes made")
        return

    fixed = 0
    for r in rows:
        code, date, close, vol, amt, ratio = r
        new_vol = vol * 100
        new_amt = int(amt * 100)
        cur.execute("""
            UPDATE kline_data SET volume = ?, amount = ?
            WHERE stock_code = ? AND trade_date = ?
        """, (new_vol, new_amt, code, date))
        fixed += 1

    db.commit()
    log.info(f"Fixed {fixed:,} rows")

    # Verify 上汽
    cur.execute("""
        SELECT trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE stock_code = 'sh600104'
          AND trade_date BETWEEN '2026-06-25' AND '2026-08-11'
        ORDER BY trade_date
    """)
    log.info("\n=== 上汽 sh600104 (after fix) ===")
    for r in cur.fetchall():
        log.info(f"  {r[0]}: 收盘{r[1]}, 量{r[2]:,}手, 额{r[3]:,.0f}, ratio={r[4]:.4f}")

    # Watchlist summary
    cur.execute("""
        SELECT w.stock_code,
               AVG(CASE WHEN k.amount>0 THEN k.amount/(k.volume*100.0*k.close) END) as avg_ratio,
               SUM(CASE WHEN k.amount=0 THEN 1 ELSE 0 END) as zero_amt
        FROM watchlist w
        JOIN kline_data k ON w.stock_code = k.stock_code
        GROUP BY w.stock_code
        ORDER BY avg_ratio
    """)
    log.info("\n=== Watchlist (after fix) ===")
    for r in cur.fetchall():
        code, ratio, zero = r
        status = "✅" if ratio and ratio > 0.7 else ("⚠️" if ratio else "❌")
        log.info(f"  {status} {code}: ratio={round(ratio,4) if ratio else 'N/A'}, zero_amt={zero}")

    db.close()

if __name__ == "__main__":
    main()