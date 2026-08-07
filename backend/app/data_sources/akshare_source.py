"""
akshare data source — HTTP（东财/新浪等）
用途：复权因子计算、股票搜索（含拼音）、K线备份
限流：东财接口间隔 ≥1s
"""
from app.data_sources.manager import BaseDataSource, DataSourceError
from datetime import datetime, timezone
import logging
import asyncio
import time
import os

logger = logging.getLogger(__name__)

# Bypass system proxy for domestic China data sources.
# macOS system proxy (127.0.0.1:10808) intercepts requests/urllib3 at OS level;
# env vars alone are insufficient, so we monkey-patch requests.Session.
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

import requests as _requests

_orig_session_init = _requests.Session.__init__

def _patched_session_init(self, *args, **kwargs):
    _orig_session_init(self, *args, **kwargs)
    self.trust_env = False  # ignore system proxy settings
    self.proxies = {"http": None, "https": None}
    self.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

_requests.Session.__init__ = _patched_session_init

# Module-level stock list cache (loaded once)
_stock_cache: list[dict] | None = None
_stock_cache_time: float = 0


async def _load_stock_list_async() -> list[dict]:
    """Load and cache A-share stock list from eastmoney API via httpx."""
    global _stock_cache, _stock_cache_time
    if _stock_cache is not None and time.time() - _stock_cache_time < 86400:
        return _stock_cache

    import httpx

    url = "https://80.push2.eastmoney.com/api/qt/clist/get"
    stocks = []
    page = 1
    PAGE_SIZE = 5000

    async with httpx.AsyncClient(timeout=15, proxy=None, trust_env=False, http1=True, http2=False) as client:
        while True:
            params = {
                "pn": str(page),
                "pz": str(PAGE_SIZE),
                "po": "1",
                "np": "1",
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14",
            }
            resp = await client.get(url, params=params)
            data = resp.json().get("data", {})
            diff = data.get("diff", [])
            if not diff:
                break
            for item in diff:
                code = str(item.get("f12", "")).strip()
                name = str(item.get("f14", "")).strip()
                if not code or not name:
                    continue
                prefix = "sh" if code.startswith("6") else "sz"
                stocks.append({
                    "code": f"{prefix}{code}",
                    "name": name,
                    "pinyin": _to_pinyin_initials(name),
                })
            total = data.get("total", 0)
            if page * PAGE_SIZE >= total:
                break
            page += 1

    _stock_cache = stocks
    _stock_cache_time = time.time()
    logger.info(f"Loaded {len(stocks)} stocks from eastmoney")
    return stocks


def _to_pinyin_initials(name: str) -> str:
    """Convert Chinese name to pinyin initials (e.g. 贵州茅台 → gzmt)."""
    try:
        from pypinyin import pinyin, Style
        initials = pinyin(name, style=Style.FIRST_LETTER)
        return "".join([p[0] for p in initials]).lower()
    except ImportError:
        return ""


class AkshareSource(BaseDataSource):
    name = "akshare"

    async def _safe_call(self, func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        import akshare as ak

        try:
            df = await self._safe_call(
                ak.stock_zh_a_hist,
                symbol=code[2:],
                period="daily",
                adjust="",
            )
            await asyncio.sleep(1)  # rate limit

            data = []
            for _, row in df.iterrows():
                date_str = str(row["日期"])[:10]
                ts_ms = int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
                data.append({
                    "timestamp": ts_ms,
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": int(row["成交量"]),
                    "turnover": float(row.get("成交额", 0)),
                })
            return data
        except Exception as e:
            logger.error(f"akshare kline error: {e}")
            raise DataSourceError(f"akshare kline: {e}")

    async def fetch_realtime(self, codes: list[str]) -> dict:
        raise DataSourceError("akshare realtime not implemented, use easyquotation")

    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        """Compute adjust factors by comparing qfq and raw prices from eastmoney API.
        factor = raw_close / qfq_close (latest date factor = 1.0)
        Uses httpx directly to bypass system proxy issues with akshare/requests.
        """
        import httpx

        pure_code = code[2:]
        secid = f"1.{pure_code}" if pure_code.startswith("6") else f"0.{pure_code}"
        base_url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        params_tpl = {
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "klt": "101",
            "secid": secid,
            "beg": "19700101",
            "end": "20500101",
        }

        try:
            async with httpx.AsyncClient(timeout=15, proxy=None, trust_env=False, http1=True, http2=False) as client:
                # fqt=0 → raw (none), fqt=1 → qfq
                resp_raw = await client.get(base_url, params={**params_tpl, "fqt": "0"})
                await asyncio.sleep(1)
                resp_qfq = await client.get(base_url, params={**params_tpl, "fqt": "1"})

            raw_data = resp_raw.json().get("data", {})
            qfq_data = resp_qfq.json().get("data", {})
            raw_klines = raw_data.get("klines", [])
            qfq_klines = qfq_data.get("klines", [])

            if not raw_klines or not qfq_klines:
                return []

            # Parse: "date,open,close,high,low,volume,amount,amplitude"
            raw_map = {}
            for line in raw_klines:
                parts = line.split(",")
                raw_map[parts[0]] = float(parts[2])  # close

            factors = []
            for line in qfq_klines:
                parts = line.split(",")
                date_str = parts[0]
                qfq_close = float(parts[2])
                raw_close = raw_map.get(date_str)
                if raw_close and qfq_close > 0:
                    factor = round(raw_close / qfq_close, 6)
                else:
                    factor = 1.0
                factors.append({"trade_date": date_str, "factor": factor})
            return factors
        except Exception as e:
            logger.error(f"akshare adjust error: {e}")
            raise DataSourceError(f"akshare adjust: {e}")

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        """Search stocks using mootdx TCP stock list (bypasses proxy issues)."""
        try:
            from mootdx.quotes import Quotes
            import asyncio

            loop = asyncio.get_event_loop()

            def _fetch():
                client = Quotes.factory(market="std")
                df_sh = client.stocks(market=1)
                df_sz = client.stocks(market=0)
                return df_sh, df_sz

            df_sh, df_sz = await loop.run_in_executor(None, _fetch)

            # Filter A-share stocks (60/00/30/68 prefix)
            stocks = []
            for df, prefix in [(df_sh, "sh"), (df_sz, "sz")]:
                for _, row in df.iterrows():
                    code = str(row["code"]).strip()
                    name = str(row["name"]).strip()
                    # Only A-share stocks
                    if not (code.startswith(("60", "00", "30", "68"))):
                        continue
                    stocks.append({
                        "code": f"{prefix}{code}",
                        "name": name,
                        "pinyin": _to_pinyin_initials(name),
                    })

            # Search
            kw = keyword.lower().strip()
            results = []
            for s in stocks:
                score = 0
                if s["code"].lower().startswith(kw) or s["code"][2:].startswith(kw):
                    score += 10
                if kw in s["name"].lower():
                    score += 5
                if s["pinyin"] and s["pinyin"].startswith(kw):
                    score += 3
                if score > 0:
                    results.append((score, s))
            results.sort(key=lambda x: -x[0])
            return [r[1] for r in results[:limit]]
        except Exception as e:
            logger.error(f"akshare search error: {e}")
            raise DataSourceError(f"akshare search: {e}")