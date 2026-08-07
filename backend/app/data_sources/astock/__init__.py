"""
astock — A股全栈数据源模块（异步版）。

从 a-stock-data 项目提取并改造为 httpx.AsyncClient 异步实现，集成到 FastAPI 架构。
所有东财请求走 helpers.em_get()/em_post()（内置 asyncio.Lock 串行限流 + 会话复用），
非东财请求（同花顺/巨潮/财联社）用独立 httpx 请求。

子模块:
    helpers      — 限流请求、市场前缀、数据中心统一查询
    signal       — 资金流向/概念板块/解禁/北向/龙虎榜/行业排名/板块资金流
    news         — 个股新闻/财联社电报/全球资讯
    announcement — 巨潮公告
    report       — 个股研报/一致预期EPS
    fundamental  — 基本面/股东户数/分红/融资融券
    board        — 涨停池/打板情绪
    sentiment    — 同花顺热榜/东财人气榜

应用退出时调用 close_client() 关闭复用的 httpx.AsyncClient。
"""
from .helpers import (
    UA,
    DATACENTER_URL,
    EM_MIN_INTERVAL,
    em_get,
    em_post,
    get_prefix,
    get_secid,
    eastmoney_datacenter,
    close_client,
)

from .signal import (
    fund_flow_minute,
    concept_blocks,
    lockup_expiry,
    north_flow_realtime,
    dragon_tiger,
    daily_dragon_tiger,
    industry_rank,
    board_fund_flow,
)

from .news import (
    stock_news,
    cls_telegraph,
    global_news,
)

from .announcement import (
    cninfo_announcements,
)

from .report import (
    eastmoney_reports,
    ths_eps_forecast,
)

from .fundamental import (
    stock_info,
    holder_num_change,
    dividend_history,
    margin_trading,
)

from .board import (
    limit_up_pool,
    limit_up_sentiment,
)

from .sentiment import (
    ths_hot_list,
    em_hot_rank,
)

__all__ = [
    # helpers
    "UA", "DATACENTER_URL", "EM_MIN_INTERVAL",
    "em_get", "em_post", "get_prefix", "get_secid",
    "eastmoney_datacenter", "close_client",
    # signal
    "fund_flow_minute", "concept_blocks", "lockup_expiry", "north_flow_realtime",
    "dragon_tiger", "daily_dragon_tiger", "industry_rank", "board_fund_flow",
    # news
    "stock_news", "cls_telegraph", "global_news",
    # announcement
    "cninfo_announcements",
    # report
    "eastmoney_reports", "ths_eps_forecast",
    # fundamental
    "stock_info", "holder_num_change", "dividend_history", "margin_trading",
    # board
    "limit_up_pool", "limit_up_sentiment",
    # sentiment
    "ths_hot_list", "em_hot_rank",
]
