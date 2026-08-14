#!/usr/bin/env python3
"""
Fix kline_data rows where volume is in 'shares' (not lots) and amount is in 'hundred-yuan' (not yuan).

Detection: ratio = amount / (volume * 100 * close) < 0.1
If ratio < 0.1 and volume > 1000000:
  - volume is in shares → divide by 100
  - amount is in hundred-yuan → multiply by 100
  - verify: new_ratio = (amount*100) / ((volume/100) * 100 * close) = amount * 10000 / (volume * 100 * close)
"""
import sqlite3, logging, os, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    
    # Audit: find all rows with ratio < 0.1
    cur.execute("""
        SELECT stock_code, trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE amount > 0 AND volume > 1000000 AND close > 0
          AND amount/(volume*100.0*close) < 0.1
        ORDER BY stock_code, trade_date
    """)
    bad_rows = cur.fetchall()
    log.info(f"Found {len(bad_rows)} rows with ratio < 0.1 and volume > 1M")
    
    # Group by stock to see the pattern
    from collections import defaultdict
    by_stock = defaultdict(list)
    for r in bad_rows:
        by_stock[r[0]].append(r)
    
    log.info(f"Affected stocks: {len(by_stock)}")
    for code, rows in sorted(by_stock.items())[:5]:
        ratios = [r[5] for r in rows[:3]]
        log.info(f"  {code}: {len(rows)} rows, sample ratios: {ratios[:3]}")
    
    if '--dry-run' in sys.argv:
        log.info("DRY RUN mode, no changes made")
        return
    
    # Fix: volume /= 100, amount *= 100
    fixed = 0
    for r in bad_rows:
        code, date, close, vol, amt, ratio = r
        new_vol = int(vol / 100)
        new_amt = int(amt * 100)
        cur.execute("""
            UPDATE kline_data 
            SET volume = ?, amount = ?
            WHERE stock_code = ? AND trade_date = ?
        """, (new_vol, new_amt, code, date))
        fixed += 1
    
    db.commit()
    log.info(f"Fixed {fixed} rows: volume/=100, amount*=100")
    
    # Verify
    cur.execute("""
        SELECT COUNT(*) FROM kline_data
        WHERE amount > 0 AND volume > 1000000 AND close > 0
          AND amount/(volume*100.0*close) < 0.1
    """)
    remaining = cur.fetchone()[0]
    log.info(f"Remaining ratio<0.1 rows: {remaining}")
    
    # Show a sample
    cur.execute("""
        SELECT stock_code, trade_date, close, volume, amount,
               amount/(volume*100.0*close) as ratio
        FROM kline_data
        WHERE stock_code = 'sh600900' AND trade_date BETWEEN '2020-02-10' AND '2020-02-20'
        ORDER BY trade_date
    """)
    log.info("\n=== 长江电力 2020-02-10~20 (after fix) ===")
    for r in cur.fetchall():
        log.info(f"  {r[1]}: 收盘{r[2]}, 量{r[3]:,}手, 额{r[4]:,.0f}, ratio={r[5]:.4f}")
    
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