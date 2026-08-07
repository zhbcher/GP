"""
mootdx data source — 通达信 TCP 协议（K线/实时报价）
连接: tdx_client()（a-stock-data v3.6.0 健壮工厂：显式服务器列表+真实取数验活+多级回退）
API:
  - bars(symbol, frequency, offset) → DataFrame[open, close, high, low, vol, amount, datetime]
  - quotes(symbol=[codes]) → DataFrame[code, price, last_close, open, high, low, vol, ...]
frequency 映射: 9=日K, 5=周K, 6=月K, 11=年K
"""
from app.data_sources.manager import BaseDataSource, DataSourceError
from app.data_sources.tdx_client import tdx_client
import logging

logger = logging.getLogger(__name__)

# mootdx frequency codes
FREQ_MAP = {
    "daily": 9,
    "weekly": 5,
    "monthly": 6,
    "yearly": 11,
}

# mootdx minute frequency codes
MINUTE_FREQ_MAP = {
    "5min": 0,
    "15min": 1,
    "30min": 2,
    "60min": 3,
}


class MootdxSource(BaseDataSource):
    name = "mootdx"

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = tdx_client(market="std")
        return self._client

    def _check_available(self) -> bool:
        try:
            import mootdx  # noqa: F401
            return True
        except ImportError:
            logger.warning("mootdx not installed. Install: pip install mootdx --no-deps")
            return False

    def _fetch_bars(self, code: str, frequency: int = 9, count: int = 5000) -> list[dict]:
        client = self._get_client()
        pure_code = code[2:]  # strip sh/sz prefix
        # mootdx server caps at 800 bars per request; paginate via `start`.
        # start=0 = most recent; increasing start goes further back in history.
        PAGE = 800
        all_rows = []
        seen = set()
        start = 0
        while len(all_rows) < count:
            df = client.bars(symbol=pure_code, frequency=frequency, start=start, offset=PAGE)
            if df is None or (hasattr(df, "empty") and df.empty):
                break
            new_count = 0
            for _, row in df.iterrows():
                dt = row.get("datetime")
                if dt is None:
                    continue
                key = str(dt)
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(row)
                new_count += 1
            if new_count == 0:
                break  # no new data, reached end of history
            start += PAGE

        if not all_rows:
            return []

        result = []
        for row in all_rows:
            dt = row.get("datetime")
            # datetime column is like '2026-07-27 15:00'
            if hasattr(dt, "timestamp"):
                ts_ms = int(dt.timestamp() * 1000)
            else:
                from datetime import datetime, timezone
                ts_ms = int(datetime.strptime(str(dt)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)

            result.append({
                "timestamp": ts_ms,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row.get("vol", 0)),
                "turnover": float(row.get("amount", 0)),
            })
        # Sort ascending by time
        result.sort(key=lambda x: x["timestamp"])
        return result

    def _fetch_quotes(self, codes: list[str]) -> dict:
        client = self._get_client()
        pure_codes = [c[2:] for c in codes]
        df = client.quotes(symbol=pure_codes)
        if df is None or (hasattr(df, "empty") and df.empty):
            return {}

        result = {}
        for _, row in df.iterrows():
            code = str(row.get("code", ""))
            if not code:
                continue
            prefix = "sh" if code.startswith("6") else "sz"
            last_close = float(row.get("last_close", 0))
            price = float(row.get("price", 0))
            change_pct = round((price - last_close) / last_close * 100, 2) if last_close else 0
            result[f"{prefix}{code}"] = {
                "price": price,
                "change_pct": change_pct,
                "volume": int(row.get("vol", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "open": float(row.get("open", 0)),
                "prev_close": last_close,
            }
        return result

    async def fetch_kline(self, code: str, period: str = "daily") -> list[dict]:
        if not self._check_available():
            raise DataSourceError("mootdx not available")

        import asyncio
        freq = FREQ_MAP.get(period, 9)
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_bars, code, freq
            )
        except Exception as e:
            logger.error(f"mootdx kline error: {e}")
            raise DataSourceError(f"mootdx kline: {e}")

    async def fetch_minute_kline(self, code: str, period: str = "60min", count: int = 800) -> list[dict]:
        """Fetch minute-level K-line bars (5min/15min/30min/60min).
        Returns up to 800 recent bars. Not persisted to DB.
        Timestamps are precise to the minute (milliseconds).
        """
        if not self._check_available():
            raise DataSourceError("mootdx not available")

        import asyncio
        freq = MINUTE_FREQ_MAP.get(period)
        if freq is None:
            raise DataSourceError(f"Invalid minute period: {period}")

        def _fetch():
            client = self._get_client()
            pure_code = code[2:]
            all_rows = []
            seen = set()
            start = 0
            PAGE = 800
            while len(all_rows) < count:
                df = client.bars(symbol=pure_code, frequency=freq, start=start, offset=PAGE)
                if df is None or (hasattr(df, "empty") and df.empty):
                    break
                new_count = 0
                for _, row in df.iterrows():
                    dt = row.get("datetime")
                    if dt is None:
                        continue
                    key = str(dt)
                    if key in seen:
                        continue
                    seen.add(key)
                    all_rows.append(row)
                    new_count += 1
                if new_count == 0:
                    break
                start += PAGE

            if not all_rows:
                return []

            from datetime import datetime, timezone
            result = []
            for row in all_rows:
                dt = row.get("datetime")
                if hasattr(dt, "timestamp"):
                    ts_ms = int(dt.timestamp() * 1000)
                else:
                    ts_ms = int(datetime.strptime(str(dt)[:16], "%Y-%m-%d %H:%M").timestamp() * 1000)

                result.append({
                    "timestamp": ts_ms,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": int(row.get("vol", 0)),
                    "turnover": float(row.get("amount", 0)),
                })
            result.sort(key=lambda x: x["timestamp"])
            return result

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception as e:
            logger.error(f"mootdx minute kline error: {e}")
            raise DataSourceError(f"mootdx minute kline: {e}")

    async def fetch_realtime(self, codes: list[str]) -> dict:
        if not self._check_available():
            raise DataSourceError("mootdx not available")

        import asyncio
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_quotes, codes
            )
        except Exception as e:
            logger.error(f"mootdx realtime error: {e}")
            raise DataSourceError(f"mootdx realtime: {e}")

    async def fetch_adjust_factors(self, code: str) -> list[dict]:
        """Compute exact cumulative adjust factors from mootdx xdxr (除权除息).

        For each ex-dividend event the price ratio is:
            coeff = (prev_close - fenhong + peigujia*peigu)
                    / (prev_close * (1 + songzhuangu + peigu))
        where prev_close is the real close of the last bar before the ex-date.

        Returns one entry per event date with the RAW cumulative product
        factor = prod(coeff for events on/before date) (latest < 1, oldest events
        smallest). Callers must NOT normalize: qfq ratio = latest/factor,
        hfq ratio = 1/factor.
        """
        if not self._check_available():
            raise DataSourceError("mootdx not available")

        import asyncio
        import math

        def _compute():
            client = self._get_client()
            pure_code = code[2:]
            df = client.xdxr(symbol=pure_code)
            if df is None or df.empty:
                return []

            # Dividend/split events (category=1: 除权除息)
            events = df[df['category'] == 1].copy()
            if events.empty:
                return []

            events['date'] = events.apply(
                lambda r: f"{int(r['year'])}-{int(r['month']):02d}-{int(r['day']):02d}", axis=1
            )
            events = events.sort_values('date')

            # Full-history daily closes from mootdx (independent of DB cache)
            bars = self._fetch_bars(code, frequency=9, count=20000)
            closes = {}  # 'YYYY-MM-DD' -> close
            for b in bars:
                from datetime import datetime as _dt, timezone as _tz
                d = _dt.fromtimestamp(b["timestamp"] / 1000, tz=_tz.utc).strftime("%Y-%m-%d")
                closes[d] = b["close"]
            sorted_dates = sorted(closes.keys())

            import bisect

            def _f(row, col) -> float:
                v = row.get(col)
                if v is None:
                    return 0.0
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    return 0.0
                return 0.0 if math.isnan(v) else v

            factors = []
            cum = 1.0
            for _, row in events.iterrows():
                ex_date = row['date']
                # mootdx xdxr units: all per-10-share (每10股):
                # fenhong/peigujia = yuan per 10 shares, songzhuangu/peigu = shares per 10 shares
                fenhong = _f(row, 'fenhong') / 10.0
                songzhuan = _f(row, 'songzhuangu') / 10.0
                peigujia = _f(row, 'peigujia') / 10.0
                peigu = _f(row, 'peigu') / 10.0

                if fenhong == 0 and songzhuan == 0 and peigu == 0:
                    continue

                # prev_close: last bar strictly before ex_date
                idx = bisect.bisect_left(sorted_dates, ex_date)
                if idx == 0:
                    continue  # no history before this event, cannot compute
                prev_close = closes[sorted_dates[idx - 1]]
                if prev_close <= 0:
                    continue

                adj_price = prev_close - fenhong + peigujia * peigu
                denom = prev_close * (1 + songzhuan + peigu)
                if denom <= 0:
                    continue
                coeff = adj_price / denom
                if not (0 < coeff < 1):
                    continue  # sanity guard: ex-rights must discount

                cum *= coeff
                factors.append({'trade_date': ex_date, 'factor': round(cum, 12)})

            return factors

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _compute)
        except Exception as e:
            logger.error(f"mootdx adjust factors error: {e}")
            raise DataSourceError(f"mootdx adjust: {e}")

    async def fetch_minute(self, code: str) -> dict:
        """Fetch today's minute-level data (240 points) for intraday chart.
        Returns {prev_close, data: [{time, price, avg_price, volume}]}
        """
        if not self._check_available():
            raise DataSourceError("mootdx not available")

        import asyncio

        def _fetch():
            client = self._get_client()
            pure_code = code[2:]

            # Get prev_close from realtime quotes
            qdf = client.quotes(symbol=[pure_code])
            prev_close = 0.0
            if qdf is not None and not qdf.empty:
                prev_close = float(qdf.iloc[0].get("last_close", 0))

            # Get today's minute data (240 points: 9:30-11:30 + 13:00-15:00)
            df = client.minute(symbol=pure_code)
            if df is None or df.empty:
                return {"prev_close": prev_close, "data": []}

            # Generate timestamps: 9:30-11:29 (120 min) + 13:00-14:59 (120 min)
            from datetime import datetime, date, timedelta
            today = date.today()
            morning_start = datetime(today.year, today.month, today.day, 9, 30)
            afternoon_start = datetime(today.year, today.month, today.day, 13, 0)

            timestamps = []
            for i in range(240):
                if i < 120:
                    ts = morning_start + timedelta(minutes=i)
                else:
                    ts = afternoon_start + timedelta(minutes=i - 120)
                timestamps.append(ts.strftime("%H:%M"))

            # Calculate VWAP (avg_price)
            data = []
            cum_amount = 0.0
            cum_vol = 0
            for i, (_, row) in enumerate(df.iterrows()):
                price = float(row["price"])
                vol = int(row.get("vol", 0) or row.get("volume", 0))
                cum_amount += price * vol
                cum_vol += vol
                avg_price = round(cum_amount / cum_vol, 2) if cum_vol > 0 else price
                data.append({
                    "time": timestamps[i] if i < len(timestamps) else "",
                    "price": price,
                    "avg_price": avg_price,
                    "volume": vol,
                })

            return {"prev_close": prev_close, "data": data}

        try:
            return await asyncio.get_event_loop().run_in_executor(None, _fetch)
        except Exception as e:
            logger.error(f"mootdx minute error: {e}")
            raise DataSourceError(f"mootdx minute: {e}")

    async def search_stocks(self, keyword: str, limit: int = 20) -> list[dict]:
        raise DataSourceError("mootdx search not implemented, use akshare")