#!/usr/bin/env python3
"""Walk-forward backtest for 5 prediction models.

Reads kline_data directly from SQLite, calls each predictor's _predict_from_rows,
and computes direction accuracy at horizon=5 and horizon=10.
"""
import sys
import os
import json
import sqlite3
import types
import random
import math
from datetime import datetime

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.predictors.technical import TechnicalPredictor
from app.services.predictors.statistical import StatisticalPredictor
from app.services.predictors.monte_carlo import MonteCarloPredictor
from app.services.predictors.pattern_recognition import PatternRecognizer
from app.services.predictors.xgboost_predictor import XGBoostPredictor

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
OUTPUT_PATH = "/Users/zhoubo/GP/docs/backtest-result.json"

# Parameters
MIN_HISTORY = 150
STEP = 40
HORIZONS = [5, 10]
MONTE_CARLO_SIMS = 2000  # reduced for backtest speed
DIRECTION_THRESHOLD = 0.005  # ±0.5% for flat zone
NEUTRAL_THRESHOLD = 0.02  # ±2% for monte_carlo/xgboost neutral zone


def load_all_klines():
    """Load all kline_data into memory, grouped by stock_code, sorted by trade_date."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT stock_code, trade_date, open, high, low, close, volume, amount "
        "FROM kline_data ORDER BY stock_code, trade_date"
    )
    stocks = {}
    for row in cursor:
        code = row["stock_code"]
        obj = types.SimpleNamespace(
            stock_code=code,
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            amount=row["amount"] or 0.0,
        )
        stocks.setdefault(code, []).append(obj)
    conn.close()
    return stocks


def make_rows_slice(rows, end_idx):
    """Get rows[:end_idx+1] as SimpleNamespace objects (already are)."""
    return rows[: end_idx + 1]


def get_technical_direction(result):
    """up/down/neutral from technical predictor."""
    trend = result.get("trend", "unknown")
    if trend == "up":
        return "up"
    elif trend == "down":
        return "down"
    elif trend == "sideways":
        return "neutral"
    return "neutral"


def get_statistical_direction(result):
    """up/down/neutral from statistical predictor."""
    trend = result.get("trend")
    if trend == "up":
        return "up"
    elif trend == "down":
        return "down"
    return "neutral"


def get_monte_carlo_direction(result):
    """up/down/neutral from monte_carlo predictor."""
    prob = result.get("up_probability")
    if prob is None:
        return "neutral"
    if prob > 0.5 + NEUTRAL_THRESHOLD:
        return "up"
    elif prob < 0.5 - NEUTRAL_THRESHOLD:
        return "down"
    return "neutral"


def get_patterns_direction(result):
    """up/down/neutral from pattern_recognition predictor."""
    patterns = result.get("patterns", [])
    if not patterns:
        return "neutral"
    up_count = sum(1 for p in patterns if p.get("direction") == "up")
    down_count = sum(1 for p in patterns if p.get("direction") == "down")
    if up_count > down_count:
        return "up"
    elif down_count > up_count:
        return "down"
    return "neutral"


def get_xgboost_direction(result):
    """up/down/neutral from xgboost predictor."""
    if result.get("status") in ("not_trained", "insufficient_data"):
        return "neutral"
    prob = result.get("up_probability")
    if prob is None:
        return "neutral"
    if prob > 0.5 + NEUTRAL_THRESHOLD:
        return "up"
    elif prob < 0.5 - NEUTRAL_THRESHOLD:
        return "down"
    return "neutral"


def get_actual_direction(rows, t, horizon):
    """Determine actual price direction from t to t+horizon."""
    if t + horizon >= len(rows):
        return None
    future_close = rows[t + horizon].close
    current_close = rows[t].close
    chg = future_close / current_close - 1
    if chg > DIRECTION_THRESHOLD:
        return "up"
    elif chg < -DIRECTION_THRESHOLD:
        return "down"
    return "flat"


def run_backtest():
    print("Loading all kline data from database...")
    stocks = load_all_klines()
    print(f"Loaded {len(stocks)} stocks, total {sum(len(v) for v in stocks.values())} rows")

    # Initialize predictors
    tech = TechnicalPredictor()
    stat = StatisticalPredictor()
    # For monte_carlo, we'll monkey-patch NUM_SIMULATIONS in _predict_from_rows
    mc = MonteCarloPredictor()
    pat = PatternRecognizer()
    xgb = XGBoostPredictor()

    # Pre-train xgboost model
    print("Training XGBoost model (one-time)...")
    import asyncio
    asyncio.run(xgb.train())
    print(f"XGBoost model trained: {xgb.global_model is not None}")

    # Results storage
    results = {}
    for horizon in HORIZONS:
        results[horizon] = {
            "technical": {"total": 0, "correct": 0},
            "statistical": {"total": 0, "correct": 0},
            "monte_carlo": {"total": 0, "correct": 0},
            "patterns": {"total": 0, "correct": 0},
            "xgboost": {"total": 0, "correct": 0},
        }

    for horizon in HORIZONS:
        print(f"\n{'='*60}")
        print(f"Running backtest for horizon={horizon}")
        print(f"{'='*60}")

        sample_count = 0
        for stock_code, rows in stocks.items():
            n = len(rows)
            # Find valid prediction points
            first_valid = MIN_HISTORY  # need at least 150 rows before
            last_valid = n - horizon - 1  # need horizon rows after

            if last_valid < first_valid:
                continue

            # Sample every STEP points
            for t in range(first_valid, last_valid + 1, STEP):
                sample_count += 1

                # Get visible data
                visible_rows = make_rows_slice(rows, t)

                # Actual direction
                actual = get_actual_direction(rows, t, horizon)
                if actual is None or actual == "flat":
                    continue  # skip flat, doesn't count for accuracy

                # --- Technical ---
                try:
                    r = tech._predict_from_rows(visible_rows, days=horizon)
                    d = get_technical_direction(r)
                    if d in ("up", "down"):
                        results[horizon]["technical"]["total"] += 1
                        if d == actual:
                            results[horizon]["technical"]["correct"] += 1
                except Exception as e:
                    pass

                # --- Statistical ---
                try:
                    r = stat._predict_from_rows(visible_rows, days=horizon)
                    d = get_statistical_direction(r)
                    if d in ("up", "down"):
                        results[horizon]["statistical"]["total"] += 1
                        if d == actual:
                            results[horizon]["statistical"]["correct"] += 1
                except Exception as e:
                    pass

                # --- Monte Carlo (with reduced simulations) ---
                try:
                    # Monkey-patch by temporarily modifying the method
                    original_predict = mc._predict_from_rows.__func__
                    # We'll just call with a wrapper that reduces NUM_SIMULATIONS
                    # Actually easier: patch the source by setting a flag
                    r = _mc_predict_reduced(mc, visible_rows, days=horizon)
                    d = get_monte_carlo_direction(r)
                    if d in ("up", "down"):
                        results[horizon]["monte_carlo"]["total"] += 1
                        if d == actual:
                            results[horizon]["monte_carlo"]["correct"] += 1
                except Exception as e:
                    pass

                # --- Patterns ---
                try:
                    r = pat._predict_from_rows(visible_rows, days=horizon)
                    d = get_patterns_direction(r)
                    if d in ("up", "down"):
                        results[horizon]["patterns"]["total"] += 1
                        if d == actual:
                            results[horizon]["patterns"]["correct"] += 1
                except Exception as e:
                    pass

                # --- XGBoost ---
                try:
                    r = xgb._predict_from_rows(visible_rows, days=horizon)
                    d = get_xgboost_direction(r)
                    if d in ("up", "down"):
                        results[horizon]["xgboost"]["total"] += 1
                        if d == actual:
                            results[horizon]["xgboost"]["correct"] += 1
                except Exception as e:
                    pass

            if sample_count % 200 == 0 and sample_count > 0:
                print(f"  Processed {sample_count} sample points...")

        print(f"  Total sample points: {sample_count}")

    # Compute accuracy
    output = {}
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"{'Model':<15} {'Horizon':<10} {'Total':<8} {'Correct':<8} {'Accuracy':<10}")
    print(f"{'-'*15} {'-'*10} {'-'*8} {'-'*8} {'-'*10}")

    for horizon in HORIZONS:
        output[str(horizon)] = {}
        for model in ["technical", "statistical", "monte_carlo", "patterns", "xgboost"]:
            t = results[horizon][model]["total"]
            c = results[horizon][model]["correct"]
            acc = round(c / t, 4) if t > 0 else 0
            output[str(horizon)][model] = {"total": t, "correct": c, "accuracy": acc}
            print(f"{model:<15} {horizon:<10} {t:<8} {c:<8} {acc:<10}")

    # Write JSON output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults written to {OUTPUT_PATH}")


def _mc_predict_reduced(mc, rows, days=5):
    """Call monte_carlo _predict_from_rows with reduced NUM_SIMULATIONS."""
    if len(rows) < 20:
        return {"median": 0, "range_low": 0, "range_high": 0, "status": "insufficient_data"}

    closes = [r.close for r in rows]
    current_price = closes[-1]

    returns = []
    for i in range(1, len(closes)):
        r = math.log(closes[i] / closes[i - 1])
        if abs(r) < 0.3:
            returns.append(r)

    if len(returns) < 10:
        return {"median": current_price, "range_low": current_price * 0.98,
                "range_high": current_price * 1.02, "status": "insufficient_data"}

    mu = sum(returns) / len(returns)
    sigma = math.sqrt(sum((r - mu) ** 2 for r in returns) / len(returns))

    NUM_SIMULATIONS = MONTE_CARLO_SIMS
    final_prices = []

    for _ in range(NUM_SIMULATIONS):
        price = current_price
        for _ in range(days):
            r = random.choice(returns)
            price *= math.exp(r)
        final_prices.append(price)

    final_prices.sort()

    median = final_prices[NUM_SIMULATIONS // 2]
    range_low = final_prices[int(NUM_SIMULATIONS * 0.1)]
    range_high = final_prices[int(NUM_SIMULATIONS * 0.9)]
    up_count = sum(1 for p in final_prices if p > current_price)
    up_probability = up_count / NUM_SIMULATIONS

    return {
        "median": round(median, 2),
        "range_low": round(range_low, 2),
        "range_high": round(range_high, 2),
        "up_probability": round(up_probability, 4),
        "samples": NUM_SIMULATIONS,
        "daily_volatility": round(sigma, 4),
        "annualized_volatility": round(sigma * math.sqrt(252), 4),
        "status": "ok",
        "current_price": round(current_price, 2)
    }


if __name__ == "__main__":
    run_backtest()
