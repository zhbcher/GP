"""
astock sentiment — 舆情层。

同花顺热榜（独立 httpx，不限流）、东财人气榜（emappdata POST + push2 补名称，走限流）。
"""
import logging

import httpx

from .helpers import UA, em_get, em_post

logger = logging.getLogger(__name__)

EM_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}


async def ths_hot_list(period: str = "hour") -> list[dict]:
    """同花顺热榜（名称+人气+概念标签+排名变化）。§10.2。period: hour/day。

    返回每只: rank/code/name/heat/pct/rank_chg/concepts/tag。
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(
                "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock",
                params={"stock_type": "a", "type": period, "list_type": "normal"},
                headers={"User-Agent": UA},
            )
            lst = (r.json().get("data") or {}).get("stock_list") or []
    except Exception as e:
        logger.warning(f"ths_hot_list failed: {e}")
        return []

    out = []
    for it in lst:
        tag = it.get("tag") or {}
        out.append({
            "rank": it.get("order"),
            "code": it.get("code"),
            "name": it.get("name"),
            "heat": it.get("rate"),
            "pct": it.get("rise_and_fall"),
            "rank_chg": it.get("hot_rank_chg"),
            "concepts": tag.get("concept_tag") or [],
            "tag": tag.get("popularity_tag", ""),
        })
    return out


async def em_hot_rank(top: int = 50) -> list[dict]:
    """东财人气榜（排名 + 排名变化 + 名称/价格）。§10.2。

    返回: rank/code/name/price/pct/rank_chg。
    """
    try:
        r = await em_post(
            "https://emappdata.eastmoney.com/stockrank/getAllCurrentList",
            json_data={**EM_HOT_BODY, "marketType": "", "pageNo": 1, "pageSize": top},
            headers={"User-Agent": UA}, timeout=10.0,
        )
        data = r.json().get("data") or []
        if not data:
            return []
        # 人气榜只给带前缀代码，用 push2 ulist.np 批量补名称/价格
        secids = [("0." if it["sc"].startswith("SZ") else "1.") + it["sc"][2:] for it in data]
        u = await em_get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={"ut": "f057cbcbce2a86e2866ab8877db1d059", "fltt": "2", "invt": "2",
                    "fields": "f14,f3,f12,f2", "secids": ",".join(secids)},
            headers={"User-Agent": UA, "Referer": "https://quote.eastmoney.com/"},
            timeout=10.0,
        )
        diff = (u.json().get("data") or {}).get("diff") or []
        if isinstance(diff, dict):
            diff = list(diff.values())
        nm = {x["f12"]: (x.get("f14"), x.get("f2"), x.get("f3")) for x in diff if "f12" in x}
    except Exception as e:
        logger.warning(f"em_hot_rank failed: {e}")
        return []

    out = []
    for it in data:
        code = it["sc"][2:]
        name, price, pct = nm.get(code, ("", None, None))
        out.append({
            "rank": it["rk"],
            "code": code,
            "name": name,
            "price": price,
            "pct": pct,
            "rank_chg": it.get("hisRc"),
        })
    return out
