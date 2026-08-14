#!/usr/bin/env python3
"""
One-shot correction script for kline_data amount and volume anomalies.

Problem diagnosis:
  - Data sources return volume in different units (shares vs lots).
  - Data sources return amount in different units (yuan vs 百元).
  - _normalize_volume heuristic (>1M→/100) is wrong and never ran.
  - Sina/mootdx hardcode amount=0.0.
  - sh000568 has negative prices (whole rows invalid).

Strategy:
  For each stock_code, compute ratio = amount / (volume * 100 * close).
  - ratio ≈ 1.0   → volume and amount are both correct (yuan + lots).
  - ratio ≈ 0.01  → volume is 100x too big (shares→lots not done), amount is 100x too small (百元→yuan).
  - ratio ≈ 0.1   → volume is 100x too big but amount is correct yuan.
  - ratio ≈ 100   → volume is correct but amount is 100x too big.
  - ratio < 0.001 → amount is effectively 0 (Sina source).
  Apply correction factors per stock, then upsert.

Usage:
  cd ~/GP/backend && .venv/bin/python3 ../scripts/fix_amount_volume.py
"""
import sqlite3
import logging
import sys
import os
from collections import defaultdict
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DB_PATH = os.path.expanduser("~/GP/data/stock.db")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def audit_stock_ratios(db) -> dict:
    """For each stock, compute the median ratio = amount / (volume * 100 * close).
    Returns {stock_code: (median_ratio, count_valid)}.
    """
    cur = db.cursor()
    cur.execute("""
        SELECT stock_code, close, volume, amount
        FROM kline_data
        WHERE volume > 0 AND close > 0 AND amount > 0
        ORDER BY stock_code, trade_date
    """)
    rows = cur.fetchall()

    stock_ratios = defaultdict(list)
    for r in rows:
        ratio = r["amount"] / (r["volume"] * 100.0 * r["close"])
        if 0 < ratio < 1e6:  # sanity filter
            stock_ratios[r["stock_code"]].append(ratio)

    # Compute median ratio per stock
    result = {}
    for code, ratios in stock_ratios.items():
        sorted_r = sorted(ratios)
        n = len(sorted_r)
        if n >= 5:
            median = sorted_r[n // 2]
        elif n >= 1:
            median = sorted_r[0]
        else:
            continue
        result[code] = (median, n)

    return result


def determine_correction(median_ratio: float) -> dict:
    """Determine correction factors based on median ratio.
    Returns {vol_factor: float, amt_factor: float} or None if no correction needed.
    """
    # ratio = amount / (vol * 100 * close)
    # If ratio ≈ 1.0: all good.
    # If ratio ≈ 0.01: vol is 100x too big, amt is 100x too small.
    # If ratio ≈ 0.1: vol is 100x too big, amt is correct.
    # If ratio ≈ 100: vol is correct, amt is 100x too big.
    # If ratio is very small but not 0.01: partial correction.

    if 0.7 <= median_ratio <= 1.4:
        return {"vol_factor": 1, "amt_factor": 1, "label": "correct"}

    # Check for round factors
    for factor in [100, 1000, 10000, 100000]:
        if abs(median_ratio * factor - 1.0) < 0.3:
            return {"vol_factor": factor, "amt_factor": 1, "label": f"vol_×{factor}"}
        if abs(median_ratio * factor - 100) < 30:
            return {"vol_factor": factor, "amt_factor": 0.01, "label": f"vol_×{factor}_amt_÷100"}
        if abs(median_ratio * factor - 0.01) < 0.005:
            return {"vol_factor": factor, "amt_factor": 100, "label": f"vol_×{factor}_amt_×100"}

    # For very small ratio (Sina source, amount ~0)
    if median_ratio < 0.001:
        return {"vol_factor": 1, "amt_factor": 1, "label": "amount_too_small_cannot_fix"}

    # Generic: try to round to nearest 0.01 or 100
    if median_ratio < 0.02:
        # vol is 100x too big, amt is 100x too small
        return {"vol_factor": 100, "amt_factor": 100, "label": "generic_vol_÷100_amt_×100"}
    elif median_ratio < 0.2:
        # vol is 100x too big, amt is correct
        return {"vol_factor": 100, "amt_factor": 1, "label": "generic_vol_÷100"}
    elif median_ratio > 10:
        # amt is 100x too big
        return {"vol_factor": 1, "amt_factor": 0.01, "label": "generic_amt_÷100"}
    else:
        # Unknown — skip
        return None


def fix_stock(db, stock_code: str, vol_factor: int, amt_factor: float) -> int:
    """Apply correction to a single stock. Returns number of rows updated."""
    cur = db.cursor()
    cur.execute("""
        UPDATE kline_data
        SET volume = CAST(volume / ? AS INTEGER),
            amount = CAST(amount * ? AS INTEGER)
        WHERE stock_code = ? AND volume > 0
    """, (vol_factor, amt_factor, stock_code))
    return cur.rowcount


def remove_negative_price_rows(db) -> int:
    """Delete rows with negative close prices (sh000568 anomaly)."""
    cur = db.cursor()
    cur.execute("DELETE FROM kline_data WHERE close < 0")
    return cur.rowcount


def fix_zero_amount_rows(db) -> int:
    """For rows with amount=0 but volume>0, compute amount from vol*100*close.
    Only do this AFTER volume has been corrected.
    """
    cur = db.cursor()
    cur.execute("""
        UPDATE kline_data
        SET amount = CAST(volume * 100 * close AS INTEGER)
        WHERE amount = 0 AND volume > 0 AND close > 0
    """)
    return cur.rowcount


def validate(db) -> dict:
    """Post-fix validation report."""
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount < 0")
    neg_amt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE amount = 0 AND volume > 0")
    zero_amt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data WHERE close < 0")
    neg_close = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM kline_data")
    total = cur.fetchone()[0]

    # Check ratio for a sample of stocks
    cur.execute("""
        SELECT stock_code, COUNT(*) as cnt,
               AVG(CASE WHEN amount>0 THEN amount/(volume*100.0*close) END) as avg_ratio
        FROM kline_data
        WHERE stock_code IN (SELECT stock_code FROM watchlist)
        GROUP BY stock_code
        ORDER BY avg_ratio
    """)
    stocks_ok = 0
    stocks_bad = 0
    for r in cur.fetchall():
        if r["avg_ratio"] and 0.7 < r["avg_ratio"] < 1.4:
            stocks_ok += 1
        else:
            stocks_bad += 1
            log.warning(f"  {r['stock_code']}: ratio={r['avg_ratio']:.4f}")

    return {
        "total_rows": total,
        "neg_amount": neg_amt,
        "zero_amount_positive_vol": zero_amt,
        "neg_close": neg_close,
        "stocks_ok": stocks_ok,
        "stocks_bad": stocks_bad,
    }


def main():
    log.info("=== GP Amount/Volume Correction ===")
    db = connect()

    # Step 1: Remove negative-price rows
    log.info("Step 1: Removing negative-price rows...")
    del_count = remove_negative_price_rows(db)
    db.commit()
    log.info(f"  Deleted {del_count} rows with negative close prices")

    # Step 2: Audit — determine correction per stock
    log.info("Step 2: Auditing stock ratios...")
    stock_ratios = audit_stock_ratios(db)
    log.info(f"  Found {len(stock_ratios)} stocks with valid data")

    # Step 3: Apply corrections
    log.info("Step 3: Applying corrections...")
    corrections = {}
    for code, (median_ratio, n) in sorted(stock_ratios.items()):
        corr = determine_correction(median_ratio)
        if corr is None:
            log.warning(f"  {code}: ratio={median_ratio:.6f} (n={n}) — UNKNOWN, skipped")
            continue
        if corr["vol_factor"] == 1 and corr["amt_factor"] == 1:
            continue  # already correct
        corrections[code] = corr
        log.info(f"  {code}: ratio={median_ratio:.6f} (n={n}) → {corr['label']} "
                 f"(vol/{corr['vol_factor']}, amt×{corr['amt_factor']})")

    if not corrections:
        log.info("  No corrections needed!")
    else:
        log.info(f"  Applying {len(corrections)} corrections...")
        for code, corr in corrections.items():
            rows = fix_stock(db, code, corr["vol_factor"], corr["amt_factor"])
            if rows:
                log.info(f"    {code}: {rows} rows updated")
        db.commit()
        log.info("  Commit OK")

    # Step 4: Fix amount=0 rows (compute from volume*close)
    log.info("Step 4: Fixing amount=0 rows...")
    fixed_amt = fix_zero_amount_rows(db)
    db.commit()
    log.info(f"  Fixed {fixed_amt} rows with amount=0")

    # Step 5: Validate
    log.info("Step 5: Validation...")
    report = validate(db)
    log.info(f"  Total rows: {report['total_rows']}")
    log.info(f"  Negative amount: {report['neg_amount']}")
    log.info(f"  Zero amount with positive vol: {report['zero_amount_positive_vol']}")
    log.info(f"  Negative close: {report['neg_close']}")
    log.info(f"  Watchlist stocks OK: {report['stocks_ok']}, Bad: {report['stocks_bad']}")

    # Summary
    if report['neg_amount'] == 0 and report['neg_close'] == 0 and report['stocks_bad'] == 0:
        log.info("✅ ALL CHECKS PASSED")
    else:
        log.warning("⚠️  Some checks failed — review above")

    db.close()


if __name__ == "__main__":
    main()