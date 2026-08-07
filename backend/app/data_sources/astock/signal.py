"""
astock signal — 信号层。

个股资金流向、概念板块归属、解禁日历、北向资金、龙虎榜、行业排名、板块资金流。
东财请求走 helpers.em_get()（内置限流）；同花顺北向用独立 httpx 请求。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .helpers import UA, em_get, eastmoney_datacenter, get_secid

logger = logging.getLogger(__name__)


async def fund_flow_minute(code: str) -> list[dict]:
    """个股资金流向（分钟级，当日盘中）。东财 push2 §3.4。
    push2 被封时自动 fallback 到 push2his 日级数据。

    返回: [{time, main_net, small_net, mid_net, large_net, super_net}, ...] 单位: 元
    """
    secid = get_secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
    params = {
        "secid": secid,
        "klt": "1",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {
        "User-Agent": UA,
        "Referer": "https://quote.eastmoney.com/",
        "Origin": "https://quote.eastmoney.com",
    }
    try:
        r = await em_get(url, params=params, headers=headers, timeout=10.0)
        d = r.json()
    except Exception as e:
        logger.warning(f"fund_flow_minute {code} failed: {e}")
        d = {}

    rows = []
    for line in (d.get("data") or {}).get("klines", []) or []:
        parts = line.split(",")
        if len(parts) >= 6:
            try:
                rows.append({
                    "time": parts[0],
                    "main_net": float(parts[1]),
                    "small_net": float(parts[2]),
                    "mid_net": float(parts[3]),
                    "large_net": float(parts[4]),
                    "super_net": float(parts[5]),
                })
            except (ValueError, IndexError):
                continue

    # Fallback: push2his daily kline (different host, usually not blocked)
    if not rows:
        rows = await _fund_flow_daily_fallback(secid)

    return rows


async def _fund_flow_daily_fallback(secid: str) -> list[dict]:
    """push2his 日级资金流 fallback（取最近 1 天）。"""
    url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
    params = {
        "secid": secid, "lmt": "1", "klt": "101",
        "fields1": "f1,f2,f3,f7",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
            r = await client.get(url, params=params)
            d = r.json()
    except Exception as e:
        logger.warning(f"fund_flow_daily_fallback {secid} failed: {e}")
        return []

    rows = []
    for line in (d.get("data") or {}).get("klines", []) or []:
        parts = line.split(",")
        if len(parts) >= 6:
            try:
                rows.append({
                    "time": parts[0],
                    "main_net": float(parts[1]),
                    "small_net": float(parts[2]),
                    "mid_net": float(parts[3]),
                    "large_net": float(parts[4]),
                    "super_net": float(parts[5]),
                })
            except (ValueError, IndexError):
                continue
    return rows


async def concept_blocks(code: str) -> dict:
    """个股所属板块/概念归属（东财 slist，一次请求拿全）。§3.3。

    返回: {total, boards: [{name, code, change_pct, lead_stock}], concept_tags: [板块名...]}
    """
    secid = get_secid(code)
    params = {
        "fltt": "2", "invt": "2",
        "secid": secid,
        "spt": "3", "pi": "0", "pz": "200", "po": "1",
        "fields": "f12,f14,f3,f128",
    }
    headers = {"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"}
    try:
        r = await em_get("https://push2.eastmoney.com/api/qt/slist/get",
                         params=params, headers=headers, timeout=15.0)
        d = r.json()
    except Exception as e:
        logger.warning(f"concept_blocks {code} failed: {e}")
        return {"total": 0, "boards": [], "concept_tags": []}

    diff = (d.get("data") or {}).get("diff") or {}
    items = diff.values() if isinstance(diff, dict) else diff
    boards = []
    for it in items:
        boards.append({
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get("f3", ""),
            "lead_stock": it.get("f128", ""),
        })
    return {
        "total": len(boards),
        "boards": boards,
        "concept_tags": [b["name"] for b in boards],
    }


async def lockup_expiry(code: str, trade_date: Optional[str] = None, forward_days: int = 90) -> dict:
    """限售解禁日历（历史 + 未来 N 天待解禁）。东财 datacenter §3.6。

    trade_date: YYYY-MM-DD（默认今天）。
    返回: {history: [...], upcoming: [...]}
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    def _parse(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            out.append({
                "date": str(row.get("FREE_DATE", ""))[:10],
                "type": row.get("FREE_SHARES_TYPE", ""),
                "shares": row.get("FREE_SHARES", 0),
                "able_shares": row.get("ABLE_FREE_SHARES", 0),
                "ratio": row.get("FREE_RATIO", 0),
            })
        return out

    try:
        history_data = await eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=15,
            sort_columns="FREE_DATE", sort_types="-1",
        )
        history = _parse(history_data)

        end_date = datetime.strptime(trade_date, "%Y-%m-%d") + timedelta(days=forward_days)
        end_str = end_date.strftime("%Y-%m-%d")
        upcoming_data = await eastmoney_datacenter(
            "RPT_LIFT_STAGE",
            filter_str=f'(SECURITY_CODE="{code}")(FREE_DATE>=\'{trade_date}\')(FREE_DATE<=\'{end_str}\')',
            page_size=20,
            sort_columns="FREE_DATE", sort_types="1",
        )
        upcoming = _parse(upcoming_data)
        return {"history": history, "upcoming": upcoming}
    except Exception as e:
        logger.warning(f"lockup_expiry {code} failed: {e}")
        return {"history": [], "upcoming": []}


async def north_flow_realtime() -> dict:
    """沪深股通当日实时分钟流向（同花顺 hsgtApi）。§3.2。

    返回: {points: [{time, hgt_yi, sgt_yi}], latest: {hgt_yi, sgt_yi} | None}
    单位: 亿元。注: 深股通(sgt)盘中披露收紧后常不可靠，hgt 可用。
    """
    url = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/117.0.0.0 Safari/537.36",
        "Host": "data.hexin.cn",
        "Referer": "https://data.hexin.cn/",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            d = r.json()
    except Exception as e:
        logger.warning(f"north_flow_realtime failed: {e}")
        return {"points": [], "latest": None}

    times = d.get("time", []) or []
    hgt = d.get("hgt", []) or []
    sgt = d.get("sgt", []) or []
    n = len(times)
    points = []
    latest = None
    for i in range(n):
        h = hgt[i] if i < len(hgt) else None
        s = sgt[i] if i < len(sgt) else None
        points.append({"time": times[i], "hgt_yi": h, "sgt_yi": s})
        if h is not None:
            latest = {"hgt_yi": h, "sgt_yi": s}
    return {"points": points, "latest": latest}


async def dragon_tiger(code: str, trade_date: str, look_back: int = 30) -> dict:
    """个股龙虎榜（上榜记录 + 买卖席位 TOP5 + 机构动向）。东财 datacenter §3.5。

    trade_date: YYYY-MM-DD。
    返回: {records: [...], seats: {buy: [...], sell: [...]}, institution: {...}}
    """
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=look_back)
        start_str = start.strftime("%Y-%m-%d")

        data = await eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=f"(TRADE_DATE>='{start_str}')(TRADE_DATE<='{trade_date}')(SECURITY_CODE=\"{code}\")",
            page_size=50,
            sort_columns="TRADE_DATE", sort_types="-1",
        )
        records = []
        for row in data:
            records.append({
                "date": str(row.get("TRADE_DATE", ""))[:10],
                "reason": row.get("EXPLANATION", ""),
                "net_buy": round((row.get("BILLBOARD_NET_AMT") or 0) / 10000, 1),
                "turnover": round(float(row.get("TURNOVERRATE") or 0), 2),
            })

        seats = {"buy": [], "sell": []}
        buy_data: list[dict] = []
        sell_data: list[dict] = []
        if records:
            latest_date = records[0]["date"]
            buy_data = await eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSBUY",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="BUY", sort_types="-1",
            )
            for row in buy_data[:5]:
                seats["buy"].append({
                    "name": row.get("OPERATEDEPT_NAME", ""),
                    "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                    "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                    "net": round((row.get("NET") or 0) / 10000, 1),
                })
            sell_data = await eastmoney_datacenter(
                "RPT_BILLBOARD_DAILYDETAILSSELL",
                filter_str=f"(TRADE_DATE='{latest_date}')(SECURITY_CODE=\"{code}\")",
                page_size=10,
                sort_columns="SELL", sort_types="-1",
            )
            for row in sell_data[:5]:
                seats["sell"].append({
                    "name": row.get("OPERATEDEPT_NAME", ""),
                    "buy_amt": round((row.get("BUY") or 0) / 10000, 1),
                    "sell_amt": round((row.get("SELL") or 0) / 10000, 1),
                    "net": round((row.get("NET") or 0) / 10000, 1),
                })

        institution = {"buy_amt": 0.0, "sell_amt": 0.0, "net_amt": 0.0}
        for row in buy_data:
            if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                institution["buy_amt"] += (row.get("BUY") or 0)
        for row in sell_data:
            if str(row.get("OPERATEDEPT_CODE", "")) == "0":
                institution["sell_amt"] += (row.get("SELL") or 0)
        institution["buy_amt"] = round(institution["buy_amt"] / 10000, 1)
        institution["sell_amt"] = round(institution["sell_amt"] / 10000, 1)
        institution["net_amt"] = round(institution["buy_amt"] - institution["sell_amt"], 1)

        return {"records": records, "seats": seats, "institution": institution}
    except Exception as e:
        logger.warning(f"dragon_tiger {code} failed: {e}")
        return {"records": [], "seats": {"buy": [], "sell": []}, "institution": {"buy_amt": 0, "sell_amt": 0, "net_amt": 0}}


async def daily_dragon_tiger(trade_date: Optional[str] = None, min_net_buy: Optional[float] = None) -> dict:
    """全市场龙虎榜（当日所有上榜股票 + 净买额排名）。东财 datacenter §3.9。

    trade_date: YYYY-MM-DD（默认当日）。min_net_buy: 净买入下限（万元）。
    返回: {date, total_records, stocks: [...]}
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")
    try:
        data = await eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            filter_str=f"(TRADE_DATE>='{trade_date}')(TRADE_DATE<='{trade_date}')",
            page_size=500,
            sort_columns="BILLBOARD_NET_AMT", sort_types="-1",
        )
        if not data:
            return {"date": trade_date, "total_records": 0, "stocks": [],
                    "note": "无数据（非交易日或盘后未更新）"}

        actual_date = str(data[0].get("TRADE_DATE", ""))[:10]
        stocks = []
        for row in data:
            net_buy = (row.get("BILLBOARD_NET_AMT") or 0) / 10000
            if min_net_buy is not None and net_buy < min_net_buy:
                continue
            stocks.append({
                "code": row.get("SECURITY_CODE", ""),
                "name": row.get("SECURITY_NAME_ABBR", ""),
                "reason": row.get("EXPLANATION", ""),
                "close": row.get("CLOSE_PRICE") or 0,
                "change_pct": round(float(row.get("CHANGE_RATE") or 0), 2),
                "net_buy_wan": round(net_buy, 1),
                "buy_wan": round((row.get("BILLBOARD_BUY_AMT") or 0) / 10000, 1),
                "sell_wan": round((row.get("BILLBOARD_SELL_AMT") or 0) / 10000, 1),
                "turnover_pct": round(float(row.get("TURNOVERRATE") or 0), 2),
            })
        return {"date": actual_date, "total_records": len(stocks), "stocks": stocks}
    except Exception as e:
        logger.warning(f"daily_dragon_tiger {trade_date} failed: {e}")
        return {"date": trade_date, "total_records": 0, "stocks": []}


async def industry_rank(top_n: int = 20) -> dict:
    """全行业涨跌幅排名（东财行业板块，~100 个行业）。§3.7。

    返回: {top: [...], bottom: [...], total: int}
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": "f3",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f104,f105,f128,f136,f140,f141,f207",
    }
    headers = {"User-Agent": UA}
    try:
        r = await em_get(url, params=params, headers=headers, timeout=15.0)
        d = r.json()
    except Exception as e:
        logger.warning(f"industry_rank failed: {e}")
        return {"top": [], "bottom": [], "total": 0}

    items = (d.get("data") or {}).get("diff", []) or []
    if not items:
        return {"top": [], "bottom": [], "total": 0}

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "code": item.get("f12", ""),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "leader": item.get("f140", ""),
            "leader_change": item.get("f136", 0),
        })
    return {"top": rows[:top_n], "bottom": rows[-top_n:], "total": len(rows)}


# 板块类型 → 东财 fs 参数
_BOARD_FS = {"industry": "m:90+t:2", "concept": "m:90+t:3", "region": "m:90+t:1"}
# 周期 → (排序fid, 主力净额, 主力净占比, 涨跌幅, 领涨股name)
_BOARD_PERIOD = {
    "today": ("f62", "f62", "f184", "f3", "f204"),
    "5d": ("f164", "f164", "f165", "f109", "f257"),
    "10d": ("f174", "f174", "f175", "f160", None),
}


async def board_fund_flow(board_type: str = "industry", period: str = "today", top_n: int = 20) -> dict:
    """板块资金流向排名（按主力净流入降序）。东财 push2 §3.8。

    board_type: industry/concept/region；period: today/5d/10d。
    返回: {board_type, period, total, rows: [...]}
    """
    if board_type not in _BOARD_FS:
        logger.warning(f"board_fund_flow invalid board_type: {board_type}")
        return {"board_type": board_type, "period": period, "total": 0, "rows": []}
    if period not in _BOARD_PERIOD:
        logger.warning(f"board_fund_flow invalid period: {period}")
        return {"board_type": board_type, "period": period, "total": 0, "rows": []}

    fid, f_main, f_pct, f_chg, f_leader = _BOARD_PERIOD[period]
    fields = ["f12", "f14", f_chg, f_main, f_pct]
    if f_leader:
        fields.append(f_leader)
    if period == "today":
        fields += ["f66", "f72", "f78", "f84"]

    url = "https://push2.eastmoney.com/api/qt/clist/get"
    base = {
        "pz": "200", "po": "1", "np": "1",
        "fltt": "2", "invt": "2", "fid": fid,
        "fs": _BOARD_FS[board_type],
        "fields": ",".join(dict.fromkeys(fields)),
    }

    async def _page(pn: int):
        r = await em_get(url, params={**base, "pn": str(pn)},
                         headers={"User-Agent": UA}, timeout=15.0)
        d = r.json().get("data") or {}
        return (d.get("diff") or []), int(d.get("total") or 0)

    try:
        _PAGE = 200
        items, total = await _page(1)
        pn = 2
        while len(items) < top_n:
            if total and len(items) >= total:
                break
            more, _ = await _page(pn)
            if not more:
                break
            items += more
            pn += 1
            if len(more) < _PAGE:
                break
        total = max(total, len(items))
    except Exception as e:
        logger.warning(f"board_fund_flow {board_type}/{period} failed: {e}")
        return {"board_type": board_type, "period": period, "total": 0, "rows": []}

    rows = []
    for i, it in enumerate(items):
        row = {
            "rank": i + 1,
            "name": it.get("f14", ""),
            "code": it.get("f12", ""),
            "change_pct": it.get(f_chg, 0),
            "main_net": it.get(f_main, 0),
            "main_pct": it.get(f_pct, 0),
            "leader": it.get(f_leader, "") if f_leader else "",
        }
        if period == "today":
            row.update({
                "super_large_net": it.get("f66", 0),
                "large_net": it.get("f72", 0),
                "medium_net": it.get("f78", 0),
                "small_net": it.get("f84", 0),
            })
        rows.append(row)

    return {"board_type": board_type, "period": period, "total": total, "rows": rows[:top_n]}
