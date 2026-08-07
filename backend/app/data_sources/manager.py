"""
Data source manager with priority routing and fallback.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DataSourceError(Exception):
    pass


class BaseDataSource(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        """Return list of {timestamp, open, high, low, close, volume, turnover}"""
        ...

    @abstractmethod
    async def fetch_realtime(self, codes: list[str]) -> dict:
        """Return {code: {price, change_pct, ...}}"""
        ...

    @abstractmethod
    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        """Return list of {trade_date, factor}"""
        ...

    @abstractmethod
    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        """Return list of {code, name, pinyin}"""
        ...


class DataSourceManager:
    """Priority-based data source manager with fallback."""

    def __init__(self):
        self._sources: list[BaseDataSource] = []
        self._cache: dict[str, tuple[list[dict], datetime]] = {}

    def register(self, source: BaseDataSource):
        self._sources.append(source)

    async def get_kline(self, code: str, period: str = "daily") -> list[dict]:
        cache_key = f"kline:{code}:{period}"
        if cache_key in self._cache:
            data, ts = self._cache[cache_key]
            if datetime.now() - ts < timedelta(days=1):
                return data

        for source in self._sources:
            try:
                data = await source.fetch_kline(code, period)
                self._cache[cache_key] = (data, datetime.now())
                return data
            except Exception as e:
                logger.warning(f"{source.name} failed for kline {code}: {e}")

        # All sources failed
        if cache_key in self._cache:
            logger.warning(f"Returning stale cache for {code}")
            return self._cache[cache_key][0]
        raise DataSourceError(f"All sources failed for kline {code}")

    async def get_realtime(self, codes: list[str]) -> dict:
        for source in self._sources:
            try:
                return await source.fetch_realtime(codes)
            except Exception as e:
                logger.warning(f"{source.name} failed for realtime: {e}")
        return {}

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        for source in self._sources:
            try:
                results = await source.search_stocks(keyword, limit)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"{source.name} failed for search: {e}")
        return []


manager = DataSourceManager()
