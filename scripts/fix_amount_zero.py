#!/usr/bin/env python3
"""
One-shot fix for amount=0 rows in kline_data.

Problem: Sina source doesn't return amount, and volume is in "shares" not "lots".
So amount=0 rows also have volume that's 100x too big.

Fix: For each row with amount=0 and volume>0 and close>0:
  1. volume /= 100 (shares → lots)
  2. amount = volume * 100 * close (compute from corrected volume)

Usage:
  cd ~/GP/backend && .venv/bin/python3 ../scripts/fix_amount_zero.py
"""
import sqlite3, logging, os
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

def main():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    
    # 1. Count amount=0 rows
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount = 0 AND volume > 0 AND close > 0")
    total = cur.fetchone()[0]
    log.info(f"Rows with amount=0 and volume>0: {total}")
    
    # 2. Check volume units for these rows
    # If volume is in "shares" (too big by 100x), fix both volume and amount
    cur.execute("""
        SELECT stock_code, trade_date, close, volume, amount
        FROM kline_data
        WHERE amount = 0 AND volume > 0 AND close > 0
        ORDER BY stock_code, trade_date
    """)
    rows = cur.fetchall()
    
    from collections import defaultdict
    stock_vols = defaultdict(list)
    for r in rows:
        stock_vols[r[0]].append(r)
    
    fixed_vol = 0
    fixed_amt = 0
    for code, stock_rows in stock_vols.items():
        # For each stock, check if volume is in shares (need /100) or in lots
        # Use non-zero amount rows as reference
        cur.execute("""
            SELECT volume, amount, close FROM kline_data 
            WHERE stock_code = ? AND amount > 0 AND volume > 0 AND close > 0
            LIMIT 1
        """, (code,))
        ref = cur.fetchone()
        
        if ref:
            ref_vol, ref_amt, ref_close = ref
            ref_ratio = ref_amt / (ref_vol * 100.0 * ref_close) if ref_vol*100*ref_close > 0 else 0
        else:
            ref_ratio = None
        
        for r in stock_rows:
            _, date, close, vol, _ = r
            if ref_ratio and ref_ratio > 0.7:
                # Reference data is in lots, so this row volume is also in lots
                # Just compute amount
                new_amt = int(vol * 100 * close)
                cur.execute("UPDATE kline_data SET amount = ? WHERE stock_code = ? AND trade_date = ?",
                           (new_amt, code, date))
                fixed_amt += 1
            else:
                # No reference data or ref is also wrong
                # Assume volume is in shares → convert to lots
                new_vol = vol // 100
                if new_vol > 0:
                    new_amt = int(new_vol * 100 * close)
                    cur.execute("UPDATE kline_data SET volume = ?, amount = ? WHERE stock_code = ? AND trade_date = ?",
                               (new_vol, new_amt, code, date))
                    fixed_vol += 1
                    fixed_amt += 1
                else:
                    # Volume too small after /100, just compute amount from original
                    new_amt = int(vol * 100 * close)
                    cur.execute("UPDATE kline_data SET amount = ? WHERE stock_code = ? AND trade_date = ?",
                               (new_amt, code, date))
                    fixed_amt += 1
    
    db.commit()
    log.info(f"Fixed: {fixed_vol} rows with volume corrected, {fixed_amt} rows with amount filled")
    
    # 3. Verify
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount = 0 AND volume > 0")
    remaining = cur.fetchone()[0]
    log.info(f"Remaining amount=0 rows: {remaining}")
    
    # 4. Check watchlist
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
        if ratio and ratio > 0.7:
            status = "✅"
        elif ratio:
            status = "⚠️"
        else:
            status = "❌"
        log.info(f"  {status} {code}: ratio={ratio:.4f if ratio else 0}, zero_amt={zero}")
    
    db.close()

if __name__ == "__main__":
    main()