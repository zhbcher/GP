"""
astock report — 研报层。

个股研报+评级+EPS（东财 reportapi）、一致预期EPS（同花顺 basic.10jqka.com.cn）。
东财请求走 helpers.em_get()；同花顺用独立 httpx 请求。
"""
import logging
import re

import httpx

from .helpers import em_get

logger = logging.getLogger(__name__)

REPORT_API = "https://reportapi.eastmoney.com/report/list"


async def eastmoney_reports(code: str, limit: int = 10) -> list[dict]:
    """个股研报列表（含评级 + 三年 EPS 预测）。东财 reportapi §2.1。

    返回: [{title, publish_date, org, rating, industry, info_code,
            eps_this_year, eps_next_year, eps_next_two_year}]
    """
    params = {
        "industryCode": "*", "pageSize": str(max(limit, 100)), "industry": "*",
        "rating": "*", "ratingChange": "*",
        "beginTime": "2000-01-01", "endTime": "2030-01-01",
        "pageNo": "1", "fields": "", "qType": "0",
        "orgCode": "", "code": code, "rcode": "",
        "p": "1", "pageNum": "1", "pageNumber": "1",
    }
    try:
        r = await em_get(REPORT_API, params=params,
                         headers={"Referer": "https://data.eastmoney.com/"}, timeout=30.0)
        d = r.json()
    except Exception as e:
        logger.warning(f"eastmoney_reports {code} failed: {e}")
        return []

    rows = []
    for rec in (d.get("data") or [])[:limit]:
        rows.append({
            "title": rec.get("title", ""),
            "publish_date": (rec.get("publishDate") or "")[:10],
            "org": rec.get("orgSName", ""),
            "rating": rec.get("emRatingName", ""),
            "industry": rec.get("indvInduName", ""),
            "info_code": rec.get("infoCode", ""),
            "eps_this_year": rec.get("predictThisYearEps"),
            "eps_next_year": rec.get("predictNextYearEps"),
            "eps_next_two_year": rec.get("predictNextTwoYearEps"),
        })
    return rows


def _parse_eps_table(html: str) -> list[dict]:
    """从同花顺 worth.html 里解析「业绩预测」表格 → list[dict]。

    目标表头: 年度 / 预测机构数 / 最小值 / 均值 / 最大值 / 行业平均数。
    返回每行: {year, org_count, min, mean, max}（行业平均数省略）。
    """
    def _norm(s: str) -> str:
        if "年度" in s or "年份" in s:
            return "year"
        if "机构数" in s or "预测机构" in s:
            return "org_count"
        if "最小" in s:
            return "min"
        if "行业平均" in s:
            return "industry_avg"  # 行业平均数，非本股一致预期，需与「均值」区分
        if "均值" in s or "平均" in s:
            return "mean"
        if "最大" in s:
            return "max"
        return s

    tables = re.findall(r"<table.*?</table>", html, flags=re.DOTALL | re.IGNORECASE)
    for table in tables:
        tr_blocks = re.findall(r"<tr.*?>(.*?)</tr>", table, flags=re.DOTALL | re.IGNORECASE)
        if len(tr_blocks) < 2:
            continue
        # 第一行作表头
        header_cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr_blocks[0], flags=re.DOTALL | re.IGNORECASE)
        headers = [_norm(re.sub(r"<[^>]+>", "", c).strip()) for c in header_cells]
        # 必须同时含 年度 与 均值 才是目标预测表
        if "year" not in headers or "mean" not in headers:
            continue

        result = []
        for tr in tr_blocks[1:]:
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.DOTALL | re.IGNORECASE)
            if not cells:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            rec = {}
            for i, val in enumerate(clean):
                if i < len(headers):
                    rec[headers[i]] = val
            # 只保留核心 5 列
            result.append({
                "year": rec.get("year", ""),
                "org_count": rec.get("org_count", ""),
                "min": rec.get("min", ""),
                "mean": rec.get("mean", ""),
                "max": rec.get("max", ""),
            })
        if result:
            return result
    return []


async def ths_eps_forecast(code: str) -> list[dict]:
    """同花顺机构一致预期 EPS（直连 basic.10jqka.com.cn，解析 HTML 表格）。§2.2。

    返回: [{year, org_count, min, mean, max}]，"mean" = 机构一致预期 EPS。
    预测机构数 < 3 的需谨慎。
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://basic.10jqka.com.cn/",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            html = r.content.decode("gbk", errors="ignore")
    except Exception as e:
        logger.warning(f"ths_eps_forecast {code} failed: {e}")
        return []

    try:
        return _parse_eps_table(html)
    except Exception as e:
        logger.warning(f"ths_eps_forecast {code} parse failed: {e}")
        return []
