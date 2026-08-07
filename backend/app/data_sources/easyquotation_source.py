from app.data_sources.manager import BaseDataSource, DataSourceError
import logging

logger = logging.getLogger(__name__)


class EasyquotationSource(BaseDataSource):
    name = "easyquotation"

    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        raise DataSourceError("easyquotation has no kline data")

    async def fetch_realtime(self, codes: list[str]) -> dict:
        try:
            import easyquotation
            import asyncio
            loop = asyncio.get_event_loop()
            q = easyquotation.use("sina")
            data = await loop.run_in_executor(None, lambda: q.real([c[2:] for c in codes]))

            result = {}
            for code, info in data.items():
                prefix = "sh" if code.startswith("6") else "sz"
                result[f"{prefix}{code}"] = {
                    "price": float(info.get("now", 0)),
                    "change_pct": float(info.get("涨跌幅", 0)),
                    "volume": int(info.get("成交量", 0)),
                    "high": float(info.get("最高", 0)),
                    "low": float(info.get("最低", 0)),
                    "open": float(info.get("今开", 0)),
                    "prev_close": float(info.get("昨收", 0)),
                }
            return result
        except Exception as e:
            logger.error(f"easyquotation realtime error: {e}")
            raise DataSourceError(f"easyquotation: {e}")

    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        raise DataSourceError("easyquotation has no adjust factors")

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        raise DataSourceError("easyquotation has no search")
