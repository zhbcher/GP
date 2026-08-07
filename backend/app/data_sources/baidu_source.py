from app.data_sources.manager import BaseDataSource, DataSourceError
import logging

logger = logging.getLogger(__name__)


class BaiduSource(BaseDataSource):
    name = "baidu"

    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        raise DataSourceError("baidu source kline not implemented")

    async def fetch_realtime(self, codes: list[str]) -> dict:
        raise DataSourceError("baidu source realtime not implemented")

    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        raise DataSourceError("baidu source adjust not implemented")

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        raise DataSourceError("baidu source search not implemented")
