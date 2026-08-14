#!/usr/bin/env python3
"""
Full kline_data cleanup - ALL 3012 stocks.

5 patterns, detected per-row:

Pattern A: ratio < 0.001
  → vol÷100, amt×100  (Sina: vol in shares, amt in 100-yuan)

Pattern E: ratio 0.005-0.05 AND vol>100K
  → vol÷100  (Sina: vol in shares, amt correct in yuan)

Pattern C: close < 0
  → zero out entire row

Pattern D: ratio > 2.0
  → amt = vol * 100 * close  (amount too large)

Usage: cd ~/GP/backend && .venv/bin/python3 ../scripts/fix_all_amounts.py
"""
import sqlite3, logging, os, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    log.info("=== BEFORE ===")
    checks = [
        ("ratio<0.001", "SELECT COUNT(*) FROM kline_data WHERE amount>0 AND volume>0 AND close>0 AND amount/(volume*100.0*close) < 0.001"),
        ("ratio 0.005-0.05 & vol>100K", "SELECT COUNT(*) FROM kline_data WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%' AND amount>0 AND volume>100000 AND close>0 AND amount/(volume*100.0*close) BETWEEN 0.005 AND 0.05"),
        ("close<0", "SELECT COUNT(*) FROM kline_data WHERE close<0"),
        ("ratio>2.0", "SELECT COUNT(*) FROM kline_data WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%' AND amount>0 AND volume>0 AND close>0 AND amount/(volume*100.0*close) > 2.0"),
    ]
    for label, sql in checks:
        cur.execute(sql)
        log.info(f"  {label:<25}: {cur.fetchone()[0]:>10,}")

    if '--dry-run' in sys.argv:
        log.info("DRY RUN"); return

    # Pattern A: ratio < 0.001
    cur.execute("""
        UPDATE kline_data SET volume = volume/100, amount = amount*100
        WHERE amount>0 AND volume>0 AND close>0
          AND amount/(volume*100.0*close) < 0.001
    """)
    log.info(f"Pattern A (ratio<0.001, vol/100+amt×100): {cur.rowcount:,}")

    # Pattern E: ratio 0.005-0.05 & vol>100K
    cur.execute("""
        UPDATE kline_data SET volume = volume/100
        WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%'
          AND amount>0 AND volume>100000 AND close>0
          AND amount/(volume*100.0*close) BETWEEN 0.005 AND 0.05
    """)
    log.info(f"Pattern E (ratio 0.005-0.05 & vol>100K, vol/100): {cur.rowcount:,}")

    # Pattern C: close<0
    cur.execute("""
        UPDATE kline_data SET open=0, high=0, low=0, close=0, volume=0, amount=0
        WHERE close<0
    """)
    log.info(f"Pattern C (close<0→zeroed): {cur.rowcount:,}")

    # Pattern D: ratio>2.0
    cur.execute("""
        UPDATE kline_data SET amount = volume*100*close
        WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%'
          AND amount>0 AND volume>0 AND close>0
          AND amount/(volume*100.0*close) > 2.0
    """)
    log.info(f"Pattern D (ratio>2.0, amt capped): {cur.rowcount:,}")

    db.commit()

    # Verify
    log.info("\n=== AFTER ===")
    for label, sql in [
        ("ratio<0.001", "SELECT COUNT(*) FROM kline_data WHERE amount>0 AND volume>0 AND close>0 AND amount/(volume*100.0*close) < 0.001"),
        ("close<0", "SELECT COUNT(*) FROM kline_data WHERE close<0"),
        ("ratio>2.0", "SELECT COUNT(*) FROM kline_data WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%' AND amount>0 AND volume>0 AND close>0 AND amount/(volume*100.0*close) > 2.0"),
    ]:
        cur.execute(sql)
        log.info(f"  {label:<25}: {cur.fetchone()[0]:>10,}")

    cur.execute("""
        SELECT
            CASE
                WHEN amount<=0 OR volume<=0 OR close<=0 THEN 'invalid'
                WHEN amount/(volume*100.0*close) < 0.5 THEN '<0.5'
                WHEN amount/(volume*100.0*close) < 0.9 THEN '0.5-0.9'
                WHEN amount/(volume*100.0*close) < 1.1 THEN '0.9-1.1'
                WHEN amount/(volume*100.0*close) < 2.0 THEN '1.1-2.0'
                ELSE '>=2.0'
            END as band, COUNT(*) as cnt
        FROM kline_data
        WHERE stock_code NOT LIKE 'sh000%' AND stock_code NOT LIKE 'sz399%'
        GROUP BY band ORDER BY band
    """)
    log.info("\nRatio distribution (non-index):")
    for r in cur.fetchall():
        log.info(f"  {r[0]:<12}: {r[1]:>12,}")

    cur.execute("""
        SELECT w.stock_code,
               AVG(CASE WHEN k.amount>0 THEN k.amount/(k.volume*100.0*k.close) END) as avg_ratio,
               SUM(CASE WHEN k.amount=0 THEN 1 ELSE 0 END) as zero_amt
        FROM watchlist w
        LEFT JOIN kline_data k ON w.stock_code=k.stock_code
        GROUP BY w.stock_code ORDER BY avg_ratio
    """)
    log.info("\nWatchlist:")
    for r in cur.fetchall():
        code, ratio, zero = r
        s = "✅" if ratio and 0.5<=ratio<=2.0 else "⚠️"
        log.info(f"  {s} {code}: ratio={round(ratio,4) if ratio else 'N/A'}, zero={zero}")

    for code in ['sh600104', 'sh600900', 'sh600099']:
        cur.execute("""
            SELECT trade_date, close, volume, amount,
                   amount/(volume*100.0*close) as ratio
            FROM kline_data
            WHERE stock_code=? AND trade_date>='2026-07-01'
              AND amount>0 AND volume>0 AND close>0
            ORDER BY trade_date DESC LIMIT 3
        """, (code,))
        for r in cur.fetchall():
            log.info(f"  {code} {r[0]}: 收{r[1]}, vol{r[2]:,}手, amt={r[3]:,.0f}, ratio={r[4]:.4f}")

    db.close()

if __name__ == "__main__":
    main()