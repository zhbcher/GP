"""
astock announcement — 公告层。

巨潮公告全文检索（含动态 orgId 查询，从 szse_stock.json 映射表，模块级异步缓存）。
巨潮非东财，用独立 httpx 请求，不需要限流。
"""
import logging
from datetime import datetime
from typing import Optional

import httpx

from .helpers import UA

logger = logging.getLogger(__name__)

# 巨潮 orgId 映射表缓存（模块级，异步懒加载）
_CNINFO_ORGID_MAP: dict[str, str] = {}
_orgid_loaded: bool = False


async def _ensure_orgid_map() -> None:
    """懒加载巨潮官方 orgId 映射表（6000+ 只股）。失败时静默降级到硬编码规则。"""
    global _CNINFO_ORGID_MAP, _orgid_loaded
    if _orgid_loaded:
        return
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(
                "http://www.cninfo.com.cn/new/data/szse_stock.json",
                headers={"User-Agent": UA},
            )
            _CNINFO_ORGID_MAP = {
                s["code"]: s["orgId"]
                for s in (r.json().get("stockList", []) or [])
                if s.get("code") and s.get("orgId")
            }
    except Exception as e:
        logger.warning(f"cninfo orgId map load failed, fallback to hardcoded: {e}")
    finally:
        _orgid_loaded = True


async def _cninfo_orgid(code: str) -> str:
    """动态查真实 orgId（#19 修复），自带硬编码 fallback。"""
    await _ensure_orgid_map()
    org = _CNINFO_ORGID_MAP.get(code)
    if org:
        return org
    # fallback：老格式（仅部分老股票适用）
    if code.startswith("6"):
        return f"gssh0{code}"
    if code.startswith(("8", "4")):
        return f"gsbj0{code}"
    return f"gssz0{code}"


def _cninfo_ts_to_date(ts: Optional[int]) -> str:
    """巨潮毫秒时间戳 → YYYY-MM-DD。"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except Exception:
        return ""


async def cninfo_announcements(code: str, limit: int = 30) -> list[dict]:
    """巨潮公告全文检索。§7.1。

    返回: [{title, type, date, url}]
    """
    url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
    try:
        org_id = await _cninfo_orgid(code)
        payload = {
            "stock": f"{code},{org_id}",
            "tabName": "fulltext",
            "pageSize": str(limit),
            "pageNum": "1",
            "column": "",
            "category": "",
            "plate": "",
            "seDate": "",
            "searchkey": "",
            "secid": "",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        headers = {
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.cninfo.com.cn/new/disclosure",
            "Origin": "https://www.cninfo.com.cn",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.post(url, data=payload, headers=headers)
            d = r.json()
    except Exception as e:
        logger.warning(f"cninfo_announcements {code} failed: {e}")
        return []

    rows = []
    for item in d.get("announcements", []) or []:
        rows.append({
            "title": item.get("announcementTitle", ""),
            "type": item.get("announcementTypeName", ""),
            "date": _cninfo_ts_to_date(item.get("announcementTime")),
            "url": f"https://www.cninfo.com.cn/new/disclosure/detail?annoId={item.get('announcementId', '')}",
        })
    return rows
