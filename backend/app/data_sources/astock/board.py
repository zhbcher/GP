"""
astock board — 打板层。

涨停池、炸板率/连板高度（东财 push2ex 四池组合）。全部走 helpers.em_get()（内置限流）。
date 参数格式 YYYYMMDD（交易日），非交易日 data 返回 null。
"""
import logging
from datetime import datetime
from typing import Optional

from .helpers import UA, em_get

logger = logging.getLogger(__name__)

ZTB_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _fmt_zt_time(t) -> str:
    """涨停板时间整数 → HH:MM:SS（92500 → 09:25:00）。"""
    s = str(t).zfill(6)
    return f"{s[0:2]}:{s[2:4]}:{s[4:6]}"


def _zt_stat(p: dict) -> str:
    """N天M板 描述。"""
    tj = p.get("zttj") or {}
    return f'{tj.get("days", "?")}天{tj.get("ct", "?")}板'


async def _em_zt_api(endpoint: str, sort: str, date: str) -> list[dict]:
    """东财涨停板行情中心通用请求（push2ex，走 em_get 限流）。

    endpoint: getTopicZTPool / getTopicZBPool / getTopicDTPool / getYesterdayZTPool
    返回 data.pool 原始列表（data 为 null = 非交易日 / 参数错）。
    """
    url = f"https://push2ex.eastmoney.com/{endpoint}"
    params = {"ut": ZTB_UT, "dpt": "wz.ztzt", "Pageindex": "0",
              "pagesize": "10000", "sort": sort, "date": date}
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = await em_get(url, params=params, headers=headers, timeout=10.0)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception as e:
        logger.warning(f"涨停板池 {endpoint} 请求失败: {e}")
        return []


async def _zt_pool(date: str) -> list[dict]:
    """涨停池原始解析。"""
    out = []
    for p in await _em_zt_api("getTopicZTPool", "fbt:asc", date):
        try:
            out.append({
                "code": p["c"], "name": p["n"], "price": p["p"] / 1000,
                "pct": round(p["zdp"], 2), "amount": p["amount"], "float_cap": p["ltsz"],
                "turnover": round(p["hs"], 2), "limit_days": p["lbc"],
                "first_seal": _fmt_zt_time(p["fbt"]), "last_seal": _fmt_zt_time(p["lbt"]),
                "seal_fund": p["fund"], "break_times": p["zbc"],
                "industry": p.get("hybk", ""), "zt_stat": _zt_stat(p),
            })
        except (KeyError, TypeError):
            continue
    return out


async def _zb_pool(date: str) -> list[dict]:
    """炸板池原始解析。"""
    out = []
    for p in await _em_zt_api("getTopicZBPool", "fbt:asc", date):
        try:
            out.append({
                "code": p["c"], "name": p["n"], "price": p["p"] / 1000,
                "limit_price": p["ztp"] / 1000, "pct": round(p["zdp"], 2),
                "turnover": round(p["hs"], 2), "first_seal": _fmt_zt_time(p["fbt"]),
                "break_times": p["zbc"], "amplitude": round(p["zf"], 2),
                "speed": round(p["zs"], 2), "industry": p.get("hybk", ""),
                "zt_stat": _zt_stat(p),
            })
        except (KeyError, TypeError):
            continue
    return out


async def _dt_pool(date: str) -> list[dict]:
    """跌停池原始解析。"""
    out = []
    for p in await _em_zt_api("getTopicDTPool", "fund:asc", date):
        try:
            out.append({
                "code": p["c"], "name": p["n"], "price": p["p"] / 1000,
                "pct": round(p["zdp"], 2), "turnover": round(p["hs"], 2), "pe": p.get("pe"),
                "seal_fund": p["fund"], "last_seal": _fmt_zt_time(p["lbt"]),
                "board_amount": p.get("fba"), "dt_days": p.get("days"),
                "open_times": p.get("oc"), "industry": p.get("hybk", ""),
            })
        except (KeyError, TypeError):
            continue
    return out


async def limit_up_pool(date: Optional[str] = None) -> list[dict]:
    """涨停池。§8.1。date=YYYYMMDD（默认今天）。

    返回每只: code/name/price/pct/amount/float_cap/turnover/limit_days(连板数)/
    first_seal/last_seal(封板时间)/seal_fund(封板资金,元)/break_times(炸板次数)/
    industry/zt_stat(N天M板)
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    return await _zt_pool(date)


async def limit_up_sentiment(date: Optional[str] = None) -> dict:
    """打板情绪温度计：连板梯队 + 炸板率 + 涨跌停对比。§8.3。

    返回: {date, zt_count, zb_count, dt_count, break_rate, max_height, ladder}
    """
    if date is None:
        date = datetime.now().strftime("%Y%m%d")
    try:
        zt = await _zt_pool(date)
        zb = await _zb_pool(date)
        dt = await _dt_pool(date)
    except Exception as e:
        logger.warning(f"limit_up_sentiment {date} failed: {e}")
        return {"date": date, "zt_count": 0, "zb_count": 0, "dt_count": 0,
                "break_rate": 0, "max_height": 0, "ladder": {}}

    ladder: dict[int, int] = {}
    for s in zt:
        ladder[s["limit_days"]] = ladder.get(s["limit_days"], 0) + 1
    zt_n, zb_n = len(zt), len(zb)
    return {
        "date": date,
        "zt_count": zt_n,
        "zb_count": zb_n,
        "dt_count": len(dt),
        "break_rate": round(zb_n / (zt_n + zb_n) * 100, 1) if (zt_n + zb_n) else 0,
        "max_height": max((s["limit_days"] for s in zt), default=0),
        "ladder": dict(sorted(ladder.items())),
    }
