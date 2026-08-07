"""MV-002: 条件筛选器 — 在自选股范围内按条件过滤."""

from typing import Any
import math

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

        # 3. Check all conditions (AND)
        all_pass = True
        for cond in req.conditions:
            if cond.type == "return_pct":
                if not _check_return_pct(closes, cond):
                    all_pass = False
                    break
            elif cond.type == "above_ma":
                if not _check_above_ma(closes, cond):
                    all_pass = False
                    break
            elif cond.type == "macd_golden_cross":
                if not _check_macd_golden_cross(closes):
                    all_pass = False
                    break
            elif cond.type == "volume_surge":
                if not _check_volume_surge(volumes, cond):
                    all_pass = False
                    break
            elif cond.type == "rsi_oversold":
                if not _check_rsi(closes, cond, oversold=True):
                    all_pass = False
                    break
            elif cond.type == "rsi_overbought":
                if not _check_rsi(closes, cond, oversold=False):
                    all_pass = False
                    break
            elif cond.type == "boll_touch_lower":
                if not _check_boll(closes, cond, lower=True):
                    all_pass = False
                    break
            elif cond.type == "boll_touch_upper":
                if not _check_boll(closes, cond, lower=False):
                    all_pass = False
                    break
            elif cond.type == "return_range":
                if not _check_return_range(closes, cond):
                    all_pass = False
                    break
            else:
                all_pass = False
                break

        if all_pass:
            results.append({
                "stock_code": item.stock_code,
                "stock_name": item.stock_name,
                "group_id": item.group_id,
                "latest_close": closes[-1],
            })

    return {"results": results, "total": len(results)}
