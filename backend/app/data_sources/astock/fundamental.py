"""
astock fundamental — 基础数据层。

个股基本面信息（东财 push2）、股东户数变化、分红送转、融资融券（东财 datacenter）。
全部走 helpers（em_get / eastmoney_datacenter，内置限流）。
"""
import logging

from .helpers import UA, em_get, eastmoney_datacenter, get_secid, get_secucode

logger = logging.getLogger(__name__)


async def stock_info(code: str) -> dict:
    """东财 F10 公司基本信息（datacenter，替代 push2）。§6.3。

    返回: {introduction, main_business, industry, list_date, chairman, emp_num}
    """
    secucode = get_secucode(code)
    try:
        data = await eastmoney_datacenter(
            "RPT_F10_BASIC_ORGINFO",
            filter_str=f'(SECUCODE="{secucode}")',
            page_size=1,
        )
    except Exception as e:
        logger.warning(f"stock_info {code} failed: {e}")
        return {}

    if not data:
        return {}
    d = data[0]
    return {
        "introduction": d.get("ORG_PROFILE", ""),
        "main_business": d.get("MAIN_BUSINESS", ""),
        "industry": d.get("EM2016", ""),
        "list_date": str(d.get("LISTING_DATE", ""))[:10],
        "chairman": d.get("CHAIRMAN", ""),
        "emp_num": d.get("EMP_NUM", 0),
    }


async def financial_indicators(code: str, limit: int = 4) -> list[dict]:
    """核心财务指标（最近 N 期）。东财 datacenter RPT_LICO_FN_CPD。

    返回: [{period, revenue, revenue_yoy, net_profit, net_profit_yoy, roe, gross_margin, eps}]
    """
    try:
        data = await eastmoney_datacenter(
            "RPT_LICO_FN_CPD",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=limit,
            sort_columns="REPORTDATE", sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"financial_indicators {code} failed: {e}")
        return []

    rows = []
    for row in data:
        rd = str(row.get("REPORTDATE", ""))[:10]
        # 2026-03-31 → 2026Q1
        period = _report_date_to_period(rd)
        rows.append({
            "period": period,
            "revenue": row.get("TOTAL_OPERATE_INCOME"),
            "revenue_yoy": row.get("YSTZ"),
            "net_profit": row.get("PARENT_NETPROFIT"),
            "net_profit_yoy": row.get("SJLTZ"),
            "roe": row.get("WEIGHTAVG_ROE"),
            "gross_margin": row.get("XSMLL"),
            "eps": row.get("BASIC_EPS"),
        })
    return rows


async def share_structure(code: str) -> list[dict]:
    """股本结构。东财 datacenter RPT_F10_EH_EQUITY。

    返回: [{name, ratio}]
    """
    secucode = get_secucode(code)
    try:
        data = await eastmoney_datacenter(
            "RPT_F10_EH_EQUITY",
            filter_str=f'(SECUCODE="{secucode}")',
            page_size=1,
            sort_columns="END_DATE", sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"share_structure {code} failed: {e}")
        return []

    if not data:
        return []
    d = data[0]
    total = d.get("TOTAL_SHARES") or 1
    rows = []
    items = [
        ("流通A股", d.get("LISTED_A_SHARES")),
        ("限售A股", d.get("LIMITED_A_SHARES")),
        ("流通B股", d.get("B_FREE_SHARE")),
        ("流通H股", d.get("H_FREE_SHARE")),
    ]
    for name, shares in items:
        if shares and shares > 0:
            rows.append({"name": name, "ratio": round(shares / total * 100, 2)})
    return rows


def _report_date_to_period(rd: str) -> str:
    """2026-03-31 → 2026Q1, 2025-12-31 → 2025Q4."""
    try:
        parts = rd.split("-")
        year = parts[0]
        month = int(parts[1])
        q = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, f"M{month:02d}")
        return f"{year}{q}"
    except Exception:
        return rd


async def holder_num_change(code: str, limit: int = 10) -> list[dict]:
    """股东户数变化（季度级）。东财 datacenter §4.3。

    返回: [{date, holder_num, change_num, change_ratio, avg_shares}]
    股东户数持续减少 = 筹码集中 = 主力吸筹信号。
    """
    try:
        data = await eastmoney_datacenter(
            "RPT_HOLDERNUMLATEST",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=limit,
            sort_columns="END_DATE", sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"holder_num_change {code} failed: {e}")
        return []

    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("END_DATE", ""))[:10],
            "holder_num": row.get("HOLDER_NUM", 0),
            "change_num": row.get("HOLDER_NUM_CHANGE", 0),
            "change_ratio": row.get("HOLDER_NUM_RATIO", 0),
            "avg_shares": row.get("AVG_FREE_SHARES", 0),
        })
    return rows


async def dividend_history(code: str, limit: int = 20) -> list[dict]:
    """分红送转历史。东财 datacenter §4.4。

    返回: [{date, bonus_rmb, transfer_ratio, bonus_ratio, plan}]
    """
    try:
        data = await eastmoney_datacenter(
            "RPT_SHAREBONUS_DET",
            filter_str=f'(SECURITY_CODE="{code}")',
            page_size=limit,
            sort_columns="EX_DIVIDEND_DATE", sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"dividend_history {code} failed: {e}")
        return []

    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("EX_DIVIDEND_DATE", ""))[:10],
            "bonus_rmb": row.get("PRETAX_BONUS_RMB", 0),
            "transfer_ratio": row.get("TRANSFER_RATIO", 0),
            "bonus_ratio": row.get("BONUS_RATIO", 0),
            "plan": row.get("ASSIGN_PROGRESS", ""),
        })
    return rows


async def margin_trading(code: str, limit: int = 30) -> list[dict]:
    """融资融券明细（日级）。东财 datacenter §4.1。

    返回: [{date, rzye, rzmre, rzche, rqye, rqmcl, rqchl, rzrqye}]
    融资余额持续增加 = 杠杆资金看多。
    """
    try:
        data = await eastmoney_datacenter(
            "RPTA_WEB_RZRQ_GGMX",
            filter_str=f'(SCODE="{code}")',
            page_size=limit,
            sort_columns="DATE", sort_types="-1",
        )
    except Exception as e:
        logger.warning(f"margin_trading {code} failed: {e}")
        return []

    rows = []
    for row in data:
        rows.append({
            "date": str(row.get("DATE", ""))[:10],
            "rzye": row.get("RZYE", 0),
            "rzmre": row.get("RZMRE", 0),
            "rzche": row.get("RZCHE", 0),
            "rqye": row.get("RQYE", 0),
            "rqmcl": row.get("RQMCL", 0),
            "rqchl": row.get("RQCHL", 0),
            "rzrqye": row.get("RZRQYE", 0),
        })
    return rows
