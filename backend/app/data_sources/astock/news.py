"""
astock news — 新闻层。

个股新闻（东财 search-api JSONP）、财联社电报（v1 API + 本地签名）、全球资讯（东财 np-weblist）。
东财请求走 helpers.em_get()；财联社用独立 httpx 请求（本地签名，零 key）。
"""
import hashlib
import json
import logging
import re
import uuid
from datetime import datetime

import httpx

from .helpers import UA, em_get

logger = logging.getLogger(__name__)


async def stock_news(code: str, limit: int = 20) -> list[dict]:
    """东财个股新闻（JSONP 接口）。§5.1。

    返回: [{title, content, time, source, url}]
    """
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                  "pageIndex": 1, "pageSize": limit, "preTag": "", "postTag": ""}},
    }, separators=(",", ":"))
    params = {"cb": cb, "param": inner_params}
    headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}
    try:
        r = await em_get(url, params=params, headers=headers, timeout=15.0)
        text = r.text
        json_str = text[text.index("(") + 1: text.rindex(")")]
        d = json.loads(json_str)
    except Exception as e:
        logger.warning(f"stock_news {code} failed: {e}")
        return []

    rows = []
    articles = (d.get("result") or {}).get("cmsArticleWebOld", []) or []
    for a in articles:
        rows.append({
            "title": re.sub(r"<[^>]+>", "", a.get("title", "")),
            "content": re.sub(r"<[^>]+>", "", a.get("content", ""))[:200],
            "time": a.get("date", ""),
            "source": a.get("mediaName", ""),
            "url": a.get("url", ""),
        })
    return rows


async def cls_telegraph(limit: int = 50) -> list[dict]:
    """财联社电报（全市场实时快讯）。v1 API + 本地签名，零 key。§5.2。

    签名: sign = md5(sha1(按 key 字典序拼接的 query 串))。
    返回: [{title, content, time}]  time 已转为 'YYYY-MM-DD HH:MM:SS'
    """
    params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5",
              "last_time": "", "refresh_type": "1", "rn": str(limit)}
    qs = "&".join(f"{k}={params[k]}" for k in sorted(params))
    sign = hashlib.md5(hashlib.sha1(qs.encode()).hexdigest().encode()).hexdigest()
    url = f"https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}"
    headers = {"User-Agent": UA, "Referer": "https://www.cls.cn/"}
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            d = r.json()
    except Exception as e:
        logger.warning(f"cls_telegraph failed: {e}")
        return []

    rows = []
    for item in (d.get("data") or {}).get("roll_data", []) or []:
        ts = item.get("ctime")
        t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
        rows.append({
            "title": item.get("title", "") or item.get("brief", ""),
            "content": item.get("content", "") or item.get("brief", ""),
            "time": t,
        })
    return rows


async def global_news(limit: int = 30) -> list[dict]:
    """东方财富全球财经资讯（7x24 滚动）。§5.3。

    返回: [{title, summary, time}]
    """
    url = "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web", "biz": "web_724",
        "fastColumn": "102", "sortEnd": "",
        "pageSize": str(limit),
        "req_trace": str(uuid.uuid4()),
    }
    headers = {"User-Agent": UA, "Referer": "https://kuaixun.eastmoney.com/"}
    try:
        r = await em_get(url, params=params, headers=headers, timeout=10.0)
        d = r.json()
    except Exception as e:
        logger.warning(f"global_news failed: {e}")
        return []

    rows = []
    for item in (d.get("data") or {}).get("fastNewsList", []) or []:
        rows.append({
            "title": item.get("title", ""),
            "summary": (item.get("summary", "") or "")[:200],
            "time": item.get("showTime", ""),
        })
    return rows
