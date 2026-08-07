"""
Stock search service.
Uses a simple in-memory index of A-share stocks.
In production, this would query akshare or a local stock list.
"""

import logging

logger = logging.getLogger(__name__)

# Minimal built-in stock list for demo
# In production, this is fetched from akshare stock_info_a_code_name()
_BUILTIN_STOCKS = [
    {"code": "sh600519", "name": "贵州茅台", "pinyin": "gzmt"},
    {"code": "sz000858", "name": "五粮液", "pinyin": "wly"},
    {"code": "sh601318", "name": "中国平安", "pinyin": "zgpa"},
    {"code": "sz000001", "name": "平安银行", "pinyin": "payh"},
    {"code": "sh600036", "name": "招商银行", "pinyin": "zsyh"},
    {"code": "sz002594", "name": "比亚迪", "pinyin": "byd"},
    {"code": "sh601899", "name": "紫金矿业", "pinyin": "zjky"},
    {"code": "sz300750", "name": "宁德时代", "pinyin": "ndsd"},
    {"code": "sh601398", "name": "工商银行", "pinyin": "gsyh"},
    {"code": "sh601857", "name": "中国石油", "pinyin": "zgsy"},
]


def search_stocks(keyword: str, limit: int = 20) -> list[dict]:
    kw = keyword.lower().strip()
    results = []
    for s in _BUILTIN_STOCKS:
        score = 0
        if s["code"].lower().startswith(kw) or s["code"].lower().endswith(kw):
            score += 10
        if kw in s["name"].lower():
            score += 5
        if s["pinyin"].startswith(kw):
            score += 3
        if score > 0:
            results.append((score, s))
    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]
