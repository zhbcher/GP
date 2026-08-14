"""MV-002: 条件筛选器 — 在自选股范围内按条件过滤."""

from typing import Any
import math
import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.watchlist import Watchlist
from app.models.kline_data import KlineData

router = APIRouter(prefix="/api/watchlist", tags=["screen"])


# ---- Request models ----

class Condition(BaseModel):
    type: str  # return_pct | above_ma | macd_golden_cross | volume_surge
               # | rsi_oversold | rsi_overbought | boll_touch_lower | boll_touch_upper | return_range
    days: int | None = None
    operator: str | None = None  # > < >= <= ==
    value: float | None = None
    ma_period: int | None = None
    multiplier: float | None = None  # for volume_surge / boll
    min_value: float | None = None   # for return_range
    max_value: float | None = None   # for return_range
    period: int | None = None        # for rsi/boll


class ScreenRequest(BaseModel):
    conditions: list[Condition]
    logic: str | None = None  # "OR" | "AND" (default: OR)

class ScreenBacktestRequest(BaseModel):
    conditions: list[Condition]
    logic: str | None = None  # "OR" | "AND"
    horizon: int | None = 5  # 预测 horizon (default 5 trading days)
    lookback: int | None = 500  # 每只股票回看多少根K线
    direction: str | None = "up"  # 预测方向: up / down


# ---- Indicator helpers ----

def _ema(values: list[float], period: int) -> list[float]:
    """Compute EMA for a list of close prices."""
    if not values:
        return []
    k = 2.0 / (period + 1)
    ema = [values[0]]
    for i in range(1, len(values)):
        ema.append(values[i] * k + ema[-1] * (1 - k))
    return ema


def _sma(values: list[float], period: int) -> list[float]:
    """Simple moving average."""
    result: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            result.append(float("nan"))
        else:
            window = values[i - period + 1 : i + 1]
            result.append(sum(window) / period)
    return result


def _compute_macd(closes: list[float]) -> tuple[list[float], list[float]]:
    """Return (dif, dea) arrays."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26)]
    dea = _ema(dif, 9)
    return dif, dea


def _compare(a: float, op: str, b: float) -> bool:
    return {
        ">": a > b,
        "<": a < b,
        ">=": a >= b,
        "<=": a <= b,
        "==": a == b,
    }.get(op, False)


# ---- Per-condition evaluators ----

def _check_return_pct(closes: list[float], cond: Condition) -> bool:
    days = cond.days or 5
    if len(closes) < days + 1:
        return False
    latest = closes[-1]
    ref = closes[-1 - days]
    if ref == 0:
        return False
    pct = (latest - ref) / ref * 100
    return _compare(pct, cond.operator or ">", cond.value or 0)


def _check_above_ma(closes: list[float], cond: Condition) -> bool:
    period = cond.ma_period or 20
    if len(closes) < period:
        return False
    ma_arr = _sma(closes, period)
    ma_val = ma_arr[-1]
    if math.isnan(ma_val):
        return False
    return closes[-1] > ma_val


def _check_macd_golden_cross(closes: list[float]) -> bool:
    if len(closes) < 35:
        return False
    dif, dea = _compute_macd(closes)
    if len(dif) < 2:
        return False
    # 前一日 DIF < DEA 且 当日 DIF >= DEA
    return dif[-2] < dea[-2] and dif[-1] >= dea[-1]


def _check_volume_surge(volumes: list[int], cond: Condition) -> bool:
    days = cond.days or 5
    mult = cond.multiplier or 2.0
    if len(volumes) < days + 1:
        return False
    avg_vol = sum(volumes[-1 - days : -1]) / days
    if avg_vol == 0:
        return False
    return volumes[-1] > avg_vol * mult


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder RSI（最后值）。"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0.0))
        losses.append(max(-chg, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _check_rsi(closes: list[float], cond: Condition, oversold: bool) -> bool:
    period = cond.period or 14
    rsi = _compute_rsi(closes, period)
    if rsi is None:
        return False
    threshold = cond.value if cond.value is not None else (30 if oversold else 70)
    return rsi <= threshold if oversold else rsi >= threshold


def _check_boll(closes: list[float], cond: Condition, lower: bool) -> bool:
    period = cond.period or 20
    mult = cond.multiplier or 2.0
    if len(closes) < period:
        return False
    window = closes[-period:]
    mid = sum(window) / period
    std = math.sqrt(sum((c - mid) ** 2 for c in window) / period)
    band = mid - mult * std if lower else mid + mult * std
    return closes[-1] <= band if lower else closes[-1] >= band


def _check_return_range(closes: list[float], cond: Condition) -> bool:
    days = cond.days or 5
    if len(closes) < days + 1:
        return False
    ref = closes[-1 - days]
    if ref == 0:
        return False
    pct = (closes[-1] - ref) / ref * 100
    lo = cond.min_value if cond.min_value is not None else float("-inf")
    hi = cond.max_value if cond.max_value is not None else float("inf")
    return lo <= pct <= hi


# ---- Main route ----

@router.post("/screen")
async def screen_stocks(req: ScreenRequest, db: AsyncSession = Depends(get_db)):
    """按条件筛选自选股，返回全部满足的股票列表."""

    # 1. Load all watchlist stocks
    wl_result = await db.execute(select(Watchlist).order_by(Watchlist.sort_order, Watchlist.id))
    watchlist_items = wl_result.scalars().all()
    if not watchlist_items:
        return {"results": [], "total": 0}

    results: list[dict[str, Any]] = []

    for item in watchlist_items:
        # 2. Load kline data for each stock (ordered by date)
        kq = (
            select(KlineData)
            .where(KlineData.stock_code == item.stock_code)
            .order_by(KlineData.trade_date)
        )
        k_result = await db.execute(kq)
        klines = k_result.scalars().all()
        if len(klines) < 2:
            continue

        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]

        # 3. Check conditions with OR / AND logic
        logic = (req.logic or "OR").upper()
        or_hit = False
        and_hit = True
        hit_conditions: list[str] = []

        for cond in req.conditions:
            passed = _evaluate_condition(closes, volumes, cond)
            if passed:
                hit_conditions.append(cond.type)

        if logic == "OR":
            all_pass = len(hit_conditions) > 0
        else:
            # AND: all conditions must pass
            all_pass = len(hit_conditions) == len(req.conditions)

        if all_pass:
            results.append({
                "stock_code": item.stock_code,
                "stock_name": item.stock_name,
                "group_id": item.group_id,
                "latest_close": closes[-1],
            })

    return {"results": results, "total": len(results), "logic": logic}


# ---- Backtest route ----

@router.post("/screen/backtest")
async def screen_backtest(req: ScreenBacktestRequest, db: AsyncSession = Depends(get_db)):
    """回测：对自选股历史K线逐日应用筛选条件，计算胜率和关键指标。

    回测方法：
    1. 对每只股票，从第 MIN_DATA 根 K 线开始，逐根判断条件是否触发
    2. 若触发，看 horizon 交易日后的收盘价方向
    3. 统计：触发次数、正确次数、胜率、平均盈亏、最大回撤
    4. 同时统计单因子胜率和 OR/AND 组合胜率
    """
    horizon = req.horizon or 5
    lookback = req.lookback or 500
    direction = (req.direction or "up").lower()
    logic = (req.logic or "OR").upper()

    # 最小数据量（RSI=14, MA20 等需要至少 40 根）
    MIN_DATA = 50

    wl_result = await db.execute(select(Watchlist).order_by(Watchlist.id))
    watchlist_items = wl_result.scalars().all()
    if not watchlist_items:
        return {"error": "watchlist_empty", "results": []}

    condition_names = [c.type for c in req.conditions]
    results_by_stock: list[dict] = []
    total_triggers = 0
    total_correct = 0
    per_factor_stats: dict[str, dict] = {}
    for name in condition_names:
        per_factor_stats[name] = {"triggers": 0, "correct": 0}

    for item in watchlist_items:
        kq = (
            select(KlineData)
            .where(KlineData.stock_code == item.stock_code)
            .order_by(KlineData.trade_date)
        )
        k_result = await db.execute(kq)
        klines = list(k_result.scalars().all())
        if len(klines) < MIN_DATA + horizon:
            continue

        closes = [k.close for k in klines]
        volumes = [k.volume for k in klines]
        dates = [k.trade_date for k in klines]

        stock_triggers = 0
        stock_correct = 0
        trades: list[dict] = []

        end_idx = len(klines) - horizon
        for t in range(MIN_DATA, end_idx):
            # 用 t 及之前的数据计算条件
            window_closes = closes[: t + 1]
            window_volumes = volumes[: t + 1]

            hit_flags: dict[str, bool] = {}
            for cond in req.conditions:
                hit_flags[cond.type] = _evaluate_condition(window_closes, window_volumes, cond)

            # 判断组合是否触发
            if logic == "OR":
                triggered = any(hit_flags.values())
            else:
                triggered = all(hit_flags.values())

            if not triggered:
                continue

            # 检查实际方向
            entry_price = closes[t]
            exit_price = closes[t + horizon]
            ret = (exit_price - entry_price) / entry_price
            actual_up = ret > 0
            if direction == "up":
                correct = actual_up
            else:
                correct = not actual_up

            triggered_factors = [k for k, v in hit_flags.items() if v]
            for f in triggered_factors:
                per_factor_stats[f]["triggers"] += 1
                if correct:
                    per_factor_stats[f]["correct"] += 1

            total_triggers += 1
            stock_triggers += 1
            if correct:
                total_correct += 1
                stock_correct += 1

            trades.append({
                "date": dates[t],
                "exit_date": dates[t + horizon],
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "return_pct": round(ret * 100, 2),
                "correct": correct,
                "hit_factors": triggered_factors,
            })

        # 计算每只股票的统计
        avg_ret = 0.0
        max_drawdown = 0.0
        peak = 1.0
        cum_ret = 1.0
        max_win = 0.0
        max_loss = 0.0
        for tr in trades:
            r = tr["return_pct"] / 100
            cum_ret *= (1 + r)
            peak = max(peak, cum_ret)
            drawdown = (peak - cum_ret) / peak
            max_drawdown = max(max_drawdown, drawdown)
            max_win = max(max_win, r)
            max_loss = min(max_loss, r)
            avg_ret += r

        n = len(trades)
        stock_wr = round(stock_correct / n * 100, 1) if n > 0 else 0
        results_by_stock.append({
            "stock_code": item.stock_code,
            "stock_name": item.stock_name,
            "triggers": n,
            "correct": stock_correct,
            "win_rate_pct": stock_wr,
            "avg_return_pct": round(avg_ret / n * 100, 2) if n > 0 else 0,
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "max_win_pct": round(max_win * 100, 2),
            "max_loss_pct": round(max_loss * 100, 2),
            "total_return_pct": round((cum_ret - 1) * 100, 2),
            "trades_sample": trades[-10:],  # 最近10笔
        })

    # 单因子统计
    factor_results = []
    for name, s in per_factor_stats.items():
        wr = round(s["correct"] / s["triggers"] * 100, 1) if s["triggers"] > 0 else 0
        factor_results.append({
            "factor": name,
            "triggers": s["triggers"],
            "correct": s["correct"],
            "win_rate_pct": wr,
        })

    # 按胜率排序
    factor_results.sort(key=lambda x: x["win_rate_pct"], reverse=True)

    overall_wr = round(total_correct / total_triggers * 100, 1) if total_triggers > 0 else 0
    return {
        "logic": logic,
        "horizon": horizon,
        "direction": direction,
        "overall": {
            "total_triggers": total_triggers,
            "correct": total_correct,
            "win_rate_pct": overall_wr,
        },
        "per_factor": factor_results,
        "per_stock": results_by_stock,
    }


def _evaluate_condition(closes: list[float], volumes: list[int], cond: Condition) -> bool:
    """统一条件评估入口。"""
    if cond.type == "return_pct":
        return _check_return_pct(closes, cond)
    elif cond.type == "above_ma":
        return _check_above_ma(closes, cond)
    elif cond.type == "macd_golden_cross":
        return _check_macd_golden_cross(closes)
    elif cond.type == "volume_surge":
        return _check_volume_surge(volumes, cond)
    elif cond.type == "rsi_oversold":
        return _check_rsi(closes, cond, oversold=True)
    elif cond.type == "rsi_overbought":
        return _check_rsi(closes, cond, oversold=False)
    elif cond.type == "boll_touch_lower":
        return _check_boll(closes, cond, lower=True)
    elif cond.type == "boll_touch_upper":
        return _check_boll(closes, cond, lower=False)
    elif cond.type == "return_range":
        return _check_return_range(closes, cond)
    return False
