#!/usr/bin/env python3
"""
One-shot correction script for kline_data amount and volume anomalies.
V2: Fixed ratio detection logic.
"""
import sqlite3, logging, sys, os
from collections import defaultdict
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)
DB_PATH = os.path.expanduser("~/GP/data/stock.db")

# Restore from backup first
import shutil, glob
backups = sorted(glob.glob(DB_PATH + ".bak.*"))
if backups:
    shutil.copy2(backups[-1], DB_PATH)
    log.info(f"Restored DB from {backups[-1]}")
else:
    log.warning("No backup found, proceeding with current DB")

def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def audit_stock_ratios(db):
    cur = db.cursor()
    cur.execute("SELECT stock_code, close, volume, amount FROM kline_data WHERE volume > 0 AND close > 0 AND amount > 0 ORDER BY stock_code, trade_date")
    rows = cur.fetchall()
    stock_ratios = defaultdict(list)
    for r in rows:
        denom = r["volume"] * 100.0 * r["close"]
        if denom > 0:
            ratio = r["amount"] / denom
            if 0 < ratio < 1e6:
                stock_ratios[r["stock_code"]].append(ratio)
    result = {}
    for code, ratios in stock_ratios.items():
        sorted_r = sorted(ratios); n = len(sorted_r)
        median = sorted_r[n // 2] if n >= 5 else (sorted_r[0] if n >= 1 else 0)
        result[code] = (median, n)
    return result

def determine_correction(median_ratio):
    # ratio = amount / (vol * 100 * close)
    # If ratio ≈ 1.0: both correct
    # If ratio ≈ 0.01: vol is 100x too big (shares not converted to lots), amt is 100x too small (百元)
    # If ratio ≈ 0.02: vol is 100x too big, amt is correct (元)
    # If ratio ≈ 0.5: vol is 2x too big, amt is correct
    # If ratio ≈ 100: vol is correct, amt is 100x too big

    if 0.7 <= median_ratio <= 1.4:
        return {"vol_div": 1, "amt_mul": 1, "label": "correct"}

    # ratio ≈ 0.01 → vol是股(÷100→手), amt是百元(×100→元)
    if 0.005 <= median_ratio <= 0.015:
        return {"vol_div": 100, "amt_mul": 100, "label": "vol_shares_amt_baiyuan"}

    # ratio ≈ 0.02 → vol是股(÷100→手), amt是元(正确)
    if 0.015 < median_ratio <= 0.03:
        return {"vol_div": 100, "amt_mul": 1, "label": "vol_shares_amt_yuan"}

    # ratio ≈ 0.05-0.5 → vol略大(2-10倍), amt是元
    if 0.03 < median_ratio <= 0.7:
        # 计算精确的 vol_div
        vol_div = round(1.0 / median_ratio)
        if 1 < vol_div < 100:
            return {"vol_div": vol_div, "amt_mul": 1, "label": f"vol_div{vol_div}"}

    # ratio > 1.4 → amt太大
    if median_ratio > 1.4:
        amt_div = round(median_ratio)
        if amt_div > 1:
            return {"vol_div": 1, "amt_mul": 1.0/amt_div, "label": f"amt_div{amt_div}"}

    log.warning(f"  UNKNOWN ratio={median_ratio:.6f}")
    return None

def fix_stock(db, code, vol_div, amt_mul):
    cur = db.cursor()
    if vol_div > 1 and amt_mul == 1:
        cur.execute("UPDATE kline_data SET volume = CAST(volume / ? AS INTEGER) WHERE stock_code = ? AND volume > 0", (vol_div, code))
    elif vol_div > 1 and amt_mul > 1:
        cur.execute("UPDATE kline_data SET volume = CAST(volume / ? AS INTEGER), amount = CAST(amount * ? AS INTEGER) WHERE stock_code = ? AND volume > 0", (vol_div, amt_mul, code))
    elif vol_div == 1 and amt_mul < 1:
        cur.execute("UPDATE kline_data SET amount = CAST(amount * ? AS INTEGER) WHERE stock_code = ? AND amount > 0", (amt_mul, code))
    return cur.rowcount

def main():
    log.info("=== V2: GP Amount/Volume Correction ===")
    db = connect()

    # Step 1: Remove negative-price rows
    cur = db.cursor()
    cur.execute("DELETE FROM kline_data WHERE close < 0")
    log.info(f"Deleted {cur.rowcount} rows with negative close")
    db.commit()

    # Step 2: Audit
    stock_ratios = audit_stock_ratios(db)
    log.info(f"Audited {len(stock_ratios)} stocks")

    # Step 3: Apply corrections
    corrections = {}
    for code, (median_ratio, n) in sorted(stock_ratios.items()):
        corr = determine_correction(median_ratio)
        if corr is None: continue
        if corr["vol_div"] == 1 and corr["amt_mul"] == 1: continue
        corrections[code] = corr
        log.info(f"  {code}: ratio={median_ratio:.6f} (n={n}) → {corr['label']} (vol/{corr['vol_div']}, amt×{corr['amt_mul']})")

    if corrections:
        for code, corr in corrections.items():
            rows = fix_stock(db, code, corr["vol_div"], corr["amt_mul"])
        db.commit()
        log.info(f"Applied {len(corrections)} corrections, commit OK")

    # Step 4: Fix amount=0 rows
    cur.execute("UPDATE kline_data SET amount = CAST(volume * 100 * close AS INTEGER) WHERE amount = 0 AND volume > 0 AND close > 0")
    log.info(f"Fixed {cur.rowcount} rows with amount=0")
    db.commit()

    # Step 5: Validate
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount < 0")
    neg = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount = 0 AND volume > 0")
    zero = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE close < 0")
    neg_close = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data")
    total = cur.fetchone()[0]

    # Check watchlist
    cur.execute("""
        SELECT stock_code, AVG(CASE WHEN amount>0 THEN amount/(volume*100.0*close) END) as avg_ratio
        FROM kline_data WHERE stock_code IN (SELECT stock_code FROM watchlist) GROUP BY stock_code ORDER BY avg_ratio
    """)
    ok = 0; bad = 0
    for r in cur.fetchall():
        if r["avg_ratio"] and 0.7 < r["avg_ratio"] < 1.4:
            ok += 1
        else:
            bad += 1
            log.warning(f"  BAD: {r['stock_code']} ratio={r['avg_ratio']:.4f}")

    log.info(f"\n=== Validation ===")
    log.info(f"Total rows: {total}")
    log.info(f"Negative amount: {neg}")
    log.info(f"Zero amount (vol>0): {zero}")
    log.info(f"Negative close: {neg_close}")
    log.info(f"Watchlist OK: {ok}, BAD: {bad}")
    if neg == 0 and zero == 0 and neg_close == 0 and bad == 0:
        log.info("✅ ALL CHECKS PASSED")
    else:
        log.warning("⚠️ Some checks failed")

    db.close()

if __name__ == "__main__":
    main()