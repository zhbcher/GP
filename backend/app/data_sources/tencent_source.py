from app.data_sources.manager import BaseDataSource, DataSourceError
import logging

logger = logging.getLogger(__name__)


class TencentSource(BaseDataSource):
    name = "tencent"

    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        raise DataSourceError("tencent source kline not implemented")

    async def fetch_realtime(self, codes: list[str]) -> dict:
        try:
            import httpx
            import urllib.parse
            import asyncio

            loop = asyncio.get_event_loop()
            symbols = ",".join(codes)

            async def _fetch():
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(
                        f"http://qt.gtimg.cn/q={symbols}",
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    return resp.text

            text = await _fetch()
            result = {}
            for line in text.strip().split(";"):
                if "=" not in line:
                    continue
                _, data = line.split("=", 1)
                fields = data.strip('"').split("~")
                if len(fields) < 45:
                    continue

                code = fields[2]
                result[code] = {
                    "price": float(fields[3]) if fields[3] else 0,
                    "change_pct": float(fields[32]) if fields[32] else 0,
                    "volume": int(fields[36]) if fields[36] else 0,
                    "high": float(fields[33]) if fields[33] else 0,
                    "low": float(fields[34]) if fields[34] else 0,
                    "open": float(fields[5]) if fields[5] else 0,
                    "prev_close": float(fields[4]) if fields[4] else 0,
                    "pe": float(fields[39]) if fields[39] else 0,
                    "pb": float(fields[46]) if fields[46] else 0,
                    "market_cap": float(fields[45]) if fields[45] else 0,
                }
            return result
        except Exception as e:
            logger.error(f"tencent realtime error: {e}")
            raise DataSourceError(f"tencent: {e}")

    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        raise DataSourceError("tencent adjust not implemented")

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        raise DataSourceError("tencent search not implemented")
