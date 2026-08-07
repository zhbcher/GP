"""
astock helpers — 东财限流请求、市场前缀路由、数据中心统一查询。

所有 eastmoney.com 请求必须走 em_get()（内置 asyncio.Lock 串行限流 + httpx.AsyncClient 复用），
避免高频被封 IP。非东财请求（同花顺/巨潮/财联社/新浪）用独立 httpx 请求，不需要限流。
"""
import asyncio
import logging
import random
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_MIN_INTERVAL = 1.0  # 两次东财请求最小间隔(秒)；批量筛选建议调大到 1.5~2

# 沪市指数白名单：与深市 000xxx 个股同段，需白名单区分
SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}

# ── 东财防封：全局节流 + 会话复用 ──────────────────────────────────────
_em_lock = asyncio.Lock()
_em_last_call: float = 0.0
_em_client: Optional[httpx.AsyncClient] = None


def _get_em_client() -> httpx.AsyncClient:
    """懒初始化复用的 httpx.AsyncClient（Keep-Alive）。"""
    global _em_client
    if _em_client is None or _em_client.is_closed:
        _em_client = httpx.AsyncClient(
            headers={"User-Agent": UA},
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _em_client


async def em_get(
    url: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15.0,
) -> httpx.Response:
    """东财统一请求入口：自动节流（串行锁 + 最小间隔 + 随机抖动）+ 复用 AsyncClient + 默认 UA。

    所有 eastmoney.com 接口都应通过它请求，避免高频被封 IP。
    """
    global _em_last_call
    async with _em_lock:
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call)
        if wait > 0:
            await asyncio.sleep(wait + random.uniform(0.1, 0.5))
        client = _get_em_client()
        try:
            resp = await client.get(url, params=params, headers=headers, timeout=timeout)
            return resp
        finally:
            _em_last_call = time.time()


async def em_post(
    url: str,
    json_data: Optional[dict] = None,
    data: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 15.0,
) -> httpx.Response:
    """东财 POST 请求入口（同样走串行限流）。用于 emappdata 等需要 POST 的接口。"""
    global _em_last_call
    async with _em_lock:
        wait = EM_MIN_INTERVAL - (time.time() - _em_last_call)
        if wait > 0:
            await asyncio.sleep(wait + random.uniform(0.1, 0.5))
        client = _get_em_client()
        try:
            resp = await client.post(url, json=json_data, data=data, headers=headers, timeout=timeout)
            return resp
        finally:
            _em_last_call = time.time()


def pure_code(code: str) -> str:
    """去掉 sh/sz/bj 前缀，返回纯 6 位代码。"""
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[2:]
    return c


def get_prefix(code: str) -> str:
    """6位代码 → 市场前缀（sh/sz/bj）。支持显式前缀 sh/sz/bj 透传以解决歧义。"""
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if c in SH_INDEX:
        return "sh"
    return "sz"


def get_secucode(code: str) -> str:
    """6位代码 → 东财 SECUCODE 格式（如 600104.SH / 000001.SZ）。"""
    prefix = get_prefix(code)
    pure = pure_code(code)
    return f"{pure}.{prefix.upper()}"


def get_secid(code: str) -> str:
    """6位代码 → 东财 secid 格式（如 1.600519 / 0.000001）。"""
    prefix = get_prefix(code)
    market = "1" if prefix == "sh" else "0"
    # 去掉显式前缀
    pure = code.lower()
    if pure.startswith(("sh", "sz", "bj")):
        pure = pure[2:]
    return f"{market}.{pure}"


async def eastmoney_datacenter(
    report_name: str,
    columns: str = "ALL",
    filter_str: str = "",
    page_size: int = 50,
    sort_columns: str = "",
    sort_types: str = "-1",
) -> list[dict]:
    """东财数据中心统一查询 — 龙虎榜/解禁/融资融券/大宗交易/股东户数/分红 共用（已内置限流）。"""
    params = {
        "reportName": report_name,
        "columns": columns,
        "filter": filter_str,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": sort_columns,
        "sortTypes": sort_types,
        "source": "WEB",
        "client": "WEB",
    }
    try:
        r = await em_get(DATACENTER_URL, params=params, timeout=15.0)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
        return []
    except Exception as e:
        logger.warning(f"eastmoney_datacenter {report_name} failed: {e}")
        return []


async def close_client():
    """关闭复用的 httpx.AsyncClient（应用退出时调用）。"""
    global _em_client
    if _em_client is not None and not _em_client.is_closed:
        await _em_client.aclose()
        _em_client = None
