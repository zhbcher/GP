"""Chip distribution (cost distribution) endpoint.

GET /api/stock/{code}/chips?days=120&decay=0.95

Algorithm:
  a. Fetch recent N daily K-line bars from kline_data table
  b. Distribute each day's volume uniformly across price bins (100 bins per day's low~high range)
  c. Apply decay factor: older volume weighted less (decay^i for i days ago)
  d. Aggregate all price bins, normalize to percentages
  e. Compute profit_ratio (below current price) and avg_cost (volume-weighted)
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.models.kline_data import KlineData

router = APIRouter(prefix="/api/stock", tags=["chips"])


@router.get("/{code}/chips")
async def get_chip_distribution(
    code: str,
    days: int = Query(120, ge=1, le=500),
    decay: float = Query(0.95, ge=0.1, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Calculate chip (cost) distribution for a stock.

    Returns price-level distribution of holding costs based on recent
    volume analysis with time decay.
    """
    # Fetch recent N days of kline data (most recent first, then reverse)
    q = (
        select(KlineData)
        .where(KlineData.stock_code == code)
        .order_by(desc(KlineData.trade_date))
        .limit(days)
    )
    result = await db.execute(q)
    rows = result.scalars().all()

    if not rows:
        return {
            "code": code,
            "current_price": 0,
            "chips": [],
            "profit_ratio": 0.0,
            "avg_cost": 0.0,
        }

    # Reverse to chronological order (oldest first)
    rows.reverse()

    # Determine global price range across all days
    global_low = min(r.low for r in rows)
    global_high = max(r.high for r in rows)
    price_span = global_high - global_low
    if price_span <= 0:
        # All same price — single bin
        current_price = rows[-1].close
        return {
            "code": code,
            "current_price": current_price,
            "chips": [{"price": current_price, "ratio": 1.0}],
            "profit_ratio": 100.0 if current_price >= global_low else 0.0,
            "avg_cost": current_price,
        }

    # Use a global bin system: 200 bins across the global price range
    NUM_BINS = 200
    bin_step = price_span / NUM_BINS
    bins = [0.0] * NUM_BINS  # accumulated weighted volume per bin

    for i, row in enumerate(rows):
        # i=0 is oldest, i=len-1 is newest
        # Weight: decay^(days_ago) where days_ago = (len-1 - i)
        days_ago = len(rows) - 1 - i
        weight = decay ** days_ago

        day_low = row.low
        day_high = row.high
        day_range = day_high - day_low
        day_vol = row.volume

        if day_range <= 0 or day_vol <= 0:
            # Flat day — put all volume at close price
            idx = int((row.close - global_low) / bin_step)
            idx = max(0, min(NUM_BINS - 1, idx))
            bins[idx] += day_vol * weight
            continue

        # Distribute volume across price bins within this day's range
        # Map day_low..day_high to global bin indices
        start_bin = int((day_low - global_low) / bin_step)
        end_bin = int((day_high - global_low) / bin_step)
        start_bin = max(0, start_bin)
        end_bin = min(NUM_BINS - 1, end_bin)
        num_day_bins = end_bin - start_bin + 1
        if num_day_bins <= 0:
            continue
        vol_per_bin = day_vol / num_day_bins
        for b in range(start_bin, end_bin + 1):
            bins[b] += vol_per_bin * weight

    # Normalize to percentages
    total = sum(bins)
    if total <= 0:
        current_price = rows[-1].close
        return {
            "code": code,
            "current_price": current_price,
            "chips": [],
            "profit_ratio": 0.0,
            "avg_cost": 0.0,
        }

    # Build chips list, compute avg_cost and profit_ratio
    chips = []
    profit_volume = 0.0
    cost_volume_sum = 0.0  # for weighted avg cost
    current_price = rows[-1].close

    for b in range(NUM_BINS):
        if bins[b] <= 0:
            continue
        price = global_low + (b + 0.5) * bin_step
        ratio = bins[b] / total
        chips.append({"price": round(price, 2), "ratio": round(ratio, 6)})
        if price <= current_price:
            profit_volume += bins[b]
        cost_volume_sum += price * bins[b]

    profit_ratio = round(profit_volume / total * 100, 2)
    avg_cost = round(cost_volume_sum / total, 2)

    return {
        "code": code,
        "current_price": current_price,
        "chips": chips,
        "profit_ratio": profit_ratio,
        "avg_cost": avg_cost,
    }
