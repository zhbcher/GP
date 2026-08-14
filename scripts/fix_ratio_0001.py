#!/usr/bin/env python3
"""
Fix kline_data rows with ratio < 0.001 (definitely Sina source errors).

These rows have:
  - volume in "shares" (not lots) → divide by 100
  - amount in "hundred-yuan" (not yuan) → multiply by 100

After fix, ratio should be ~1.0.

Usage:
  cd ~/GP/backend && .venv/bin/python3 ../scripts/fix_ratio_0001.py
"""
import sqlite3, logging, os
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    
    # Find rows with ratio < 0.001 (these are definitively wrong)
    cur.execute("""
        SELECT stock_code, trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE amount > 0 AND volume > 0 AND close > 0
          AND amount/(volume*100.0*close) < 0.001
        ORDER BY stock_code, trade_date
    """)
    bad_rows = cur.fetchall()
    log.info(f"Found {len(bad_rows):,} rows with ratio < 0.001")
    
    # Count by stock
    from collections import defaultdict
    by_stock = defaultdict(int)
    for r in bad_rows:
        by_stock[r[0]] += 1
    
    top_stocks = sorted(by_stock.items(), key=lambda x: -x[1])[:15]
    log.info("Top 15 affected stocks:")
    for code, cnt in top_stocks:
        log.info(f"  {code}: {cnt:,} rows")
    
    # Fix all: volume /= 100, amount *= 100
    fixed = 0
    for r in bad_rows:
        code, date, close, vol, amt, ratio = r
        new_vol = int(vol / 100)
        new_amt = int(amt * 100)
        if new_vol <= 0:
            continue  # skip degenerate cases
        cur.execute("""
            UPDATE kline_data 
            SET volume = ?, amount = ?
            WHERE stock_code = ? AND trade_date = ?
        """, (new_vol, new_amt, code, date))
        fixed += 1
    
    db.commit()
    log.info(f"Fixed {fixed:,} rows")
    
    # Verify: check remaining
    cur.execute("""
        SELECT COUNT(*) FROM kline_data
        WHERE amount > 0 AND volume > 0 AND close > 0
          AND amount/(volume*100.0*close) < 0.001
    """)
    remaining = cur.fetchone()[0]
    log.info(f"Remaining ratio<0.001: {remaining:,}")
    
    # Show sample for 长江电力
    cur.execute("""
        SELECT trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE stock_code = 'sh600900'
          AND trade_date BETWEEN '2020-02-10' AND '2020-02-20'
        ORDER BY trade_date
    """)
    log.info("\n=== 长江电力 2020-02-10~20 (after fix) ===")
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
    log.info("\n=== Watchlist after fix ===")
    for r in cur.fetchall():
        code, ratio, zero = r
        status = "✅" if ratio and ratio > 0.7 else ("⚠️" if ratio else "❌")
        log.info(f"  {status} {code}: ratio={round(ratio,4) if ratio else 'N/A'}, zero_amt={zero}")
    
    db.close()

if __name__ == "__main__":
    main()