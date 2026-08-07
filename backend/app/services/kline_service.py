from datetime import datetime, timezone, timedelta
from typing import List
from app.schemas import KlineDataRead


def _period_key(dt: datetime, period: str) -> str:
    """Generate a canonical grouping key for the given period."""
    if period == "weekly":
        # ISO week: Monday as first day
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    elif period == "monthly":
        return f"{dt.year}-{dt.month:02d}"
    elif period == "yearly":
        return str(dt.year)
    return dt.strftime("%Y-%m-%d")


def _period_start_ts(key: str, period: str) -> int:
    """Return canonical UTC midnight timestamp (ms) for a period key."""
    if period == "weekly":
        # key like "2026-W09" → Monday of that ISO week
        year, week = int(key[:4]), int(key[6:])
        jan4 = datetime(year, 1, 4, tzinfo=timezone.utc)
        start_of_week1 = jan4 - timedelta(days=jan4.weekday())
        monday = start_of_week1 + timedelta(weeks=week - 1)
        return int(monday.timestamp() * 1000)
    elif period == "monthly":
        year, month = int(key[:4]), int(key[5:7])
        return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp() * 1000)
    elif period == "yearly":
        return int(datetime(int(key), 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    # daily fallback
    return int(datetime.strptime(key, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def aggregate_period(data: List[KlineDataRead], period: str) -> List[KlineDataRead]:
    if period == "daily" or not data:
        return data

    period_map: dict[str, dict] = {}
    for d in data:
        dt = datetime.fromtimestamp(d.timestamp // 1000, tz=timezone.utc)
        key = _period_key(dt, period)

        if key not in period_map:
            period_map[key] = {
                "timestamp": _period_start_ts(key, period),
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
                "turnover": d.turnover,
            }
        else:
            agg = period_map[key]
            agg["high"] = max(agg["high"], d.high)
            agg["low"] = min(agg["low"], d.low)
            agg["close"] = d.close
            agg["volume"] += d.volume
            agg["turnover"] += d.turnover

    return [KlineDataRead(**v) for v in sorted(period_map.values(), key=lambda x: x["timestamp"])]


def compute_adjusted(
    data: List[KlineDataRead], factors: dict[str, float], adjust: str
) -> List[KlineDataRead]:
    if not factors:
        return data

    # Find latest factor for forward adjustment
    dates = sorted(factors.keys())
    if adjust == "qfq":
        latest_factor = factors[dates[-1]]
        result = []
        for d in data:
            factor = factors.get(
                datetime.fromtimestamp(d.timestamp // 1000, tz=timezone.utc).strftime("%Y-%m-%d"), 1.0
            )
            ratio = latest_factor / factor if factor else 1.0
            result.append(KlineDataRead(
                timestamp=d.timestamp,
                open=round(d.open * ratio, 2),
                high=round(d.high * ratio, 2),
                low=round(d.low * ratio, 2),
                close=round(d.close * ratio, 2),
                volume=d.volume,
                turnover=d.turnover,
            ))
        return result
    else:  # hfq
        result = []
        for d in data:
            date_key = datetime.fromtimestamp(d.timestamp // 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            factor = factors.get(date_key, 1.0)
            result.append(KlineDataRead(
                timestamp=d.timestamp,
                open=round(d.open * factor, 2),
                high=round(d.high * factor, 2),
                low=round(d.low * factor, 2),
                close=round(d.close * factor, 2),
                volume=d.volume,
                turnover=d.turnover,
            ))
        return result
