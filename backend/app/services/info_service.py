"""Info service: aggregates astock data sources with caching."""
import asyncio
import logging
import time
from typing import Any

from app.data_sources.astock import signal, news, announcement, report, fundamental, board, sentiment
from app.data_sources.astock.helpers import pure_code

logger = logging.getLogger(__name__)

# Simple in-memory cache: {key: (data, expire_ts)}
_cache: dict[str, tuple[Any, float]] = {}
_cache_lock = asyncio.Lock()


async def _cached(key: str, ttl: int, fetcher) -> Any:
    """Get from cache or fetch with TTL (seconds)."""
    now = time.time()
    if key in _cache:
        data, exp = _cache[key]
        if now < exp:
            return data
    try:
        data = await fetcher()
        _cache[key] = (data, now + ttl)
        return data
    except Exception as e:
        logger.warning(f"info_service fetch failed for {key}: {e}")
        # Return stale cache if available
        if key in _cache:
            return _cache[key][0]
        return None


# ---- Individual stock info ----

async def get_overview(code: str) -> dict:
    """Aggregate overview: valuation + fund flow + concepts + lockup risk."""
    raw_code = code  # keep original (may have sh/sz prefix)
    code = pure_code(code)
    # Valuation from tencent — realtime service needs prefixed code (sh600104)
    from app.services.realtime_service import get_realtime_quotes
    quotes = await get_realtime_quotes([raw_code])
    raw_val = quotes.get(code, {}) or next(iter(quotes.values()), {})
    # Map to frontend ValuationSnapshot format
    valuation = {
        "pe": raw_val.get("pe"),
        "pb": raw_val.get("pb"),
        "total_market_cap": (raw_val.get("market_cap") or 0) * 1e8 if raw_val.get("market_cap") else None,
        "float_market_cap": None,  # not available from tencent
        "turnover_rate": raw_val.get("turnover_rate"),
    }

    # Fund flow (5min cache) — aggregate minute data into summary
    raw_flow = await _cached(f"fund_flow:{code}", 300, lambda: signal.fund_flow_minute(code))
    fund_flow = _aggregate_fund_flow(raw_flow)

    # Concept blocks (24h cache) — extract concept_tags string array
    raw_concepts = await _cached(f"concepts:{code}", 86400, lambda: signal.concept_blocks(code))
    concepts = (raw_concepts or {}).get("concept_tags", [])

    # Lockup expiry (24h cache)
    lockup = await _cached(f"lockup:{code}", 86400, lambda: signal.lockup_expiry(code))

    return {
        "code": code,
        "valuation": valuation,
        "fund_flow": fund_flow,
        "concepts": concepts,
        "unlock_warning": lockup,
    }


def _aggregate_fund_flow(minute_data: list[dict] | None) -> dict | None:
    """Aggregate minute-level fund flow into a summary object for frontend."""
    if not minute_data:
        return None
    # Sum all minutes for today's total
    main_net = sum(d.get("main_net", 0) for d in minute_data)
    super_net = sum(d.get("super_net", 0) for d in minute_data)
    large_net = sum(d.get("large_net", 0) for d in minute_data)
    mid_net = sum(d.get("mid_net", 0) for d in minute_data)
    small_net = sum(d.get("small_net", 0) for d in minute_data)
    return {
        "main_net_inflow": main_net,
        "super_large_net": super_net,
        "large_net": large_net,
        "medium_net": mid_net,
        "small_net": small_net,
    }


async def get_news(code: str, limit: int = 20) -> list[dict]:
    """Individual stock news."""
    code = pure_code(code)
    result = await _cached(f"news:{code}:{limit}", 1800, lambda: news.stock_news(code, limit))
    return result or []


async def get_announcements(code: str, limit: int = 30) -> list[dict]:
    """Announcements from cninfo."""
    code = pure_code(code)
    result = await _cached(f"ann:{code}:{limit}", 7200, lambda: announcement.cninfo_announcements(code, limit))
    return result or []


async def get_reports(code: str, limit: int = 10) -> dict:
    """Research reports + EPS forecast."""
    code = pure_code(code)
    reports_data = await _cached(f"reports:{code}:{limit}", 86400, lambda: report.eastmoney_reports(code, limit))
    eps_data = await _cached(f"eps:{code}", 86400, lambda: report.ths_eps_forecast(code))
    return {
        "reports": reports_data or [],
        "eps_forecast": eps_data or {},
    }


async def get_finance(code: str) -> dict:
    """Core financial indicators + dividends."""
    code = pure_code(code)
    # Core indicators (revenue, profit, ROE, etc.)
    indicators = await _cached(f"indicators:{code}", 86400, lambda: fundamental.financial_indicators(code, 4))
    # Dividends — transform to frontend format
    raw_dividends = await _cached(f"dividend:{code}", 604800, lambda: fundamental.dividend_history(code))
    dividends = []
    for d in (raw_dividends or []):
        dividends.append({
            "year": (d.get("date") or "")[:4],
            "plan": f"10派{d.get('bonus_rmb', 0)}元" if d.get("bonus_rmb") else d.get("plan", ""),
            "ex_date": d.get("date", ""),
        })
    return {
        "indicators": indicators or [],
        "dividends": dividends,
    }


async def get_profile(code: str) -> dict:
    """F10 profile + holder count."""
    code = pure_code(code)
    info = await _cached(f"info:{code}", 604800, lambda: fundamental.stock_info(code))
    structure = await _cached(f"structure:{code}", 604800, lambda: fundamental.share_structure(code))
    raw_holders = await _cached(f"holders:{code}", 604800, lambda: fundamental.holder_num_change(code))
    # Transform holders to frontend format
    holders = []
    for h in (raw_holders or []):
        holders.append({
            "date": h.get("date", ""),
            "count": h.get("holder_num"),
            "change_pct": h.get("change_ratio"),
        })
    return {
        "introduction": (info or {}).get("introduction", ""),
        "main_business": (info or {}).get("main_business", ""),
        "share_structure": structure or [],
        "shareholder_count": holders,
    }


# ---- Market sentiment ----

async def get_limit_up() -> dict:
    """Limit-up pool + sentiment."""
    pool = await _cached("limit_up_pool", 600, board.limit_up_pool)
    stat = await _cached("limit_up_stat", 600, board.limit_up_sentiment)
    return {
        "pool": pool or [],
        "sentiment": stat or {},
    }


async def get_north_flow() -> Any:
    """Northbound capital flow."""
    return await _cached("north_flow", 300, signal.north_flow_realtime)


async def get_dragon_tiger(date: str | None = None) -> list[dict]:
    """Daily dragon-tiger board."""
    key = f"dragon_tiger:{date or 'today'}"
    result = await _cached(key, 3600, lambda: signal.daily_dragon_tiger(date))
    return result or []


async def get_sectors() -> dict:
    """Industry ranking + board fund flow."""
    rank = await _cached("industry_rank", 900, signal.industry_rank)
    flow = await _cached("board_flow:industry:today", 900, lambda: signal.board_fund_flow("industry", "today"))
    return {
        "rank": rank or [],
        "fund_flow": flow or [],
    }


async def get_hot_rank() -> dict:
    """Hot rank from THS + EastMoney."""
    ths = await _cached("ths_hot", 1800, sentiment.ths_hot_list)
    em = await _cached("em_hot", 1800, sentiment.em_hot_rank)
    return {
        "ths": ths or [],
        "eastmoney": em or [],
    }
