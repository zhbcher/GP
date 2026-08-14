"""
a-stock-data 集成 — 基于 simonlin1212/a-stock-data V3.6.1
数据源优先级（a-stock-data 推荐）:
  1. mootdx (通达信 TCP) — K线+五档+逐笔（国内稳定，海外可能超时）
  2. 腾讯财经 HTTP — 实时行情/PE/PB/市值（不封IP）
  3. 百度股市通 — 日K线带MA5/10/20（备用）
  4. Akshare — 最终备用（可能需翻墙）
"""
import asyncio
import json
import logging
import os
import random
import socket
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── 网络直连：数据源均为国内服务，强制绕过系统/环境代理（如 127.0.0.1:10808），
#    直连更快更稳，避免代理劫持通达信/新浪/腾讯等国内端点。 ─────────────────────
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({}))
)

# ── mootdx Client ─────────────────────────────────────────────────────────────

_TDXTCP_SERVERS = [
    ('218.75.126.9', 7709),   # ✅ 2026-08-14 实测可用：日/周/月K、五档盘口、46字段报价
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709), ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709), ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
]


def _probe_tdx(ip: str, port: int, timeout: float = 2.0) -> bool:
    """TCP 握手探测"""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def _validate_tdx(client, market: str = 'std') -> bool:
    """真实取数验活"""
    if market != 'std':
        return True
    try:
        df = client.bars(symbol='000001', frequency=9, offset=1)
        return df is not None and not df.empty
    except Exception:
        return False


_tdx_cache = {"client": None, "tried": False}


def tdx_client(market: str = 'std'):
    """创建 mootdx 客户端，规避 0.11.x BESTIP bug + 坏服务器静默空表。

    结果做进程级缓存：批量同步（如 15:30 定时任务遍历自选股）时只探测一次，
    避免每只股票重复 10×2s 的 TCP 探测。服务器恢复后重启进程即重新探测。
    """
    if _tdx_cache["tried"]:
        return _tdx_cache["client"]

    client = _tdx_client_uncached(market)
    _tdx_cache["tried"] = True
    _tdx_cache["client"] = client
    return client


def _tdx_client_uncached(market: str = 'std'):
    """mootdx 客户端探测（不缓存，供 tdx_client 调用）。

    当前环境服务器全部"握手成功但数据无响应"，单个 bars 验活约 5s，
    bestip/bare fallback 还要全局测速——整段探测可能 30s+。
    用线程 + 总超时硬限 12s，超时直接放弃 TCP 源（结果缓存，后续批次不再探测）。
    """
    import threading

    box = {"client": None}

    def _probe():
        box["client"] = _tdx_probe_inner(market)

    t = threading.Thread(target=_probe, daemon=True)
    t.start()
    t.join(timeout=12)
    if t.is_alive():
        logger.warning("mootdx probe timed out (12s), skipping TCP source")
        return None
    return box["client"]


def _tdx_probe_inner(market: str = 'std'):
    """mootdx 客户端实际探测逻辑（供 _tdx_client_uncached 在线程中调用）。"""
    try:
        from mootdx.quotes import Quotes
    except ImportError:
        logger.warning("mootdx not installed, skipping TCP source")
        return None

    MAX_PROBE = 3  # 最多验活 3 个服务器，避免无效探测拖慢批量任务
    tried = 0
    for ip, port in _TDXTCP_SERVERS:
        if tried >= MAX_PROBE:
            break
        if not _probe_tdx(ip, port, timeout=1.5):
            continue
        tried += 1
        try:
            c = Quotes.factory(market=market, server=(ip, port), timeout=3)
            if _validate_tdx(c, market):
                return c
        except Exception:
            continue

    # Fallback: bestip 测速（限时）
    try:
        c = Quotes.factory(market=market, bestip=True, timeout=3)
        if _validate_tdx(c, market):
            return c
    except Exception:
        pass

    # Last resort: bare factory（限时）
    try:
        c = Quotes.factory(market=market, timeout=3)
        if _validate_tdx(c, market):
            return c
    except Exception:
        pass

    logger.warning("All mootdx servers unreachable (overseas?)")
    return None


def fetch_mootdx_kline_sync(stock_code: str, date_str: str = "") -> tuple[str, list[dict]]:
    """Fetch daily K-line from mootdx (TCP). Returns (code, rows)."""
    client = tdx_client()
    if client is None:
        return stock_code, []

    try:
        pure_code = stock_code[2:] if stock_code[:2] in ("sh", "sz", "bj") else stock_code
        # frequency=9 = daily bar
        df = client.bars(symbol=pure_code, frequency=9, offset=1000)
        if df is None or df.empty:
            return stock_code, []

        rows = []
        for _, row in df.iterrows():
            date = str(row.get('datetime', ''))[:10]
            if date_str and date != date_str:
                continue
            rows.append({
                "trade_date": date,
                "open": float(row.get('open', 0)),
                "close": float(row.get('close', 0)),
                "high": float(row.get('high', 0)),
                "low": float(row.get('low', 0)),
                "volume": int(float(row.get('vol', 0))),
                "amount": float(row.get('amount', 0) or 0),
            })
            if date_str and date == date_str:
                break

        return stock_code, rows
    except Exception as e:
        logger.warning(f"mootdx kline failed for {stock_code}: {e}")
        return stock_code, []


async def fetch_mootdx_kline(code: str, date_str: str = "") -> list[dict]:
    """Async wrapper for mootdx kline."""
    return await asyncio.to_thread(fetch_mootdx_kline_sync, code, date_str)


# ── Tencent Realtime Quote ────────────────────────────────────────────────────

_SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}


def _tencent_prefix(code: str) -> str:
    """Convert bare 6-digit code to prefixed code for Tencent API."""
    low = code.lower()
    if low.startswith(("sh", "sz", "bj")):
        return low
    if code.startswith("92"):
        return f"bj{code}"
    if code in _SH_INDEX or code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def fetch_tencent_quotes_sync(codes: list[str]) -> dict[str, dict]:
    """Fetch realtime quotes for multiple stocks from Tencent. Returns {code: quote}."""
    prefixed = [_tencent_prefix(c) for c in codes]
    url = f"https://qt.gtimg.cn/q={','.join(prefixed)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
    except Exception as e:
        logger.warning(f"Tencent quotes failed: {e}")
        return {}

    result = {}
    for line in text.strip().split(";"):
        if "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        bare = key[2:] if key.startswith(("sh", "sz", "bj")) else key
        for orig in codes:
            orig_bare = orig[2:] if orig[:2] in ("sh", "sz", "bj") else orig
            if orig_bare == bare:
                result[orig] = {
                    "name": vals[1],
                    "price": float(vals[3]) if vals[3] else 0,
                    "prev_close": float(vals[4]) if vals[4] else 0,
                    "open": float(vals[5]) if vals[5] else 0,
                    "high": float(vals[33]) if vals[33] else 0,
                    "low": float(vals[34]) if vals[34] else 0,
                    "change_pct": float(vals[32]) if vals[32] else 0,
                    "pe_ttm": float(vals[39]) if vals[39] else 0,
                    "pb": float(vals[46]) if vals[46] else 0,
                    "mcap_yi": float(vals[45]) if vals[45] else 0,
                }
                break
    return result


async def fetch_tencent_quotes(codes: list[str]) -> dict[str, dict]:
    """Async wrapper for Tencent quotes."""
    return await asyncio.to_thread(fetch_tencent_quotes_sync, codes)


# ── HTTP 直连 session（复用）──────────────────────────────────────────────────
# 所有 HTTP 数据源强制直连：trust_env=False + 空 proxies，绕开系统/环境代理
_NO_PROXY_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _no_proxy_session():
    import requests as _req

    class _NoProxySession(_req.Session):
        def __init__(self):
            super().__init__()
            self.trust_env = False
            self.proxies = {"http": None, "https": None}

    return _NoProxySession()


def _strip_market_prefix(code: str) -> str:
    """'sh600519' / 'sz000001' / 'bj430047' -> '600519'（部分源只接受裸代码）"""
    return code[2:] if code[:2].lower() in ("sh", "sz", "bj") else code


# ── Baidu Kline with MA ───────────────────────────────────────────────────────

def fetch_baidu_kline_sync(code: str, start_time: str = "") -> Optional[dict]:
    """Fetch daily K-line with MA from Baidu. Returns parsed data or None.

    ⚠️ 百度只接受裸代码（600519），带 sh/sz 前缀时 Result 返回空 list。
    marketData 每行: 时间戳,日期,开盘,收盘,成交量,最高,最低,成交额,涨跌额,涨跌幅,换手率,均价,...
    返回 rows 按日期从旧到新排列。
    """
    import requests as _req

    session = _no_proxy_session()
    url = "https://finance.pae.baidu.com/selfselect/getstockquotation"
    params = {
        "all": "1", "isIndex": "false", "isBk": "false", "isBlock": "false",
        "isFutures": "false", "isStock": "true", "newFormat": "1",
        "group": "quotation_kline_ab", "finClientType": "pc",
        "code": _strip_market_prefix(code), "start_time": start_time, "ktype": "1",
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.finance-web.v1+json",
        "Origin": "https://gushitong.baidu.com",
        "Referer": "https://gushitong.baidu.com/",
    }
    try:
        r = session.get(url, params=params, headers=headers, timeout=10)
        d = r.json()
        result = d.get("Result", {})
        if not isinstance(result, dict):
            logger.warning(f"Baidu kline failed for {code}: Result is {type(result).__name__}")
            return None
        md = result.get("newMarketData", {})
        if not isinstance(md, dict):
            logger.warning(f"Baidu kline failed for {code}: newMarketData is {type(md).__name__}")
            return None
        keys = md.get("keys", [])
        rows_str = md.get("marketData", "")
        rows = rows_str.split(";") if rows_str else []

        if not rows or rows == [""]:
            return None

        parsed = []
        for row in rows:
            if not row.strip():
                continue
            parts = row.split(",")
            if len(parts) < 10:
                continue
            try:
                parsed.append({
                    "timestamp": int(parts[0]),
                    "date": parts[1],
                    "open": float(parts[2]),
                    "close": float(parts[3]),
                    "volume": float(parts[4]),
                    "high": float(parts[5]),
                    "low": float(parts[6]),
                    "amount": float(parts[7]),
                    "range": parts[8],
                    "ratio": parts[9],
                })
            except (ValueError, IndexError):
                continue

        return {"keys": keys, "rows": parsed}
    except Exception as e:
        logger.warning(f"Baidu kline failed for {code}: {e}")
        return None


async def fetch_baidu_kline(code: str) -> Optional[dict]:
    """Async wrapper for Baidu kline."""
    return await asyncio.to_thread(fetch_baidu_kline_sync, code)


# ── Tencent Kline (qfq 前复权, 稳定不封 IP) ───────────────────────────────────

def fetch_tencent_kline_sync(stock_code: str, date_str: str = "") -> tuple[str, list[dict]]:
    """Fetch daily K-line (前复权 qfq) from Tencent. Returns (code, rows old→new).

    Tencent fqkline 返回从旧到新排列，字段: 日期,开盘,收盘,最高,最低,成交量(手)。
    每次最多约 800 根（≈3 年日K），不封 IP，稳定直连。
    """
    import requests as _req

    session = _no_proxy_session()
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{stock_code},day,,,800,qfq"}
    try:
        r = session.get(url, params=params, headers=_NO_PROXY_HEADERS, timeout=10)
        d = r.json()
        data = d.get("data", {}).get(stock_code, {})
        rows_raw = data.get("qfqday") or []
        if not rows_raw:
            return stock_code, []

        rows = []
        for item in rows_raw:
            day = item[0]
            if date_str and day != date_str:
                continue
            try:
                rows.append({
                    "trade_date": day,
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": int(float(item[5])),
                    "amount": 0.0,
                })
            except (ValueError, IndexError):
                continue
            if date_str:
                break
        return stock_code, rows
    except Exception as e:
        logger.warning(f"Tencent kline failed for {stock_code}: {e}")
        return stock_code, []


# ── Sina Finance Kline (fallback) ────────────────────────────────────────────


def _sina_http_get_raw(host: str, path: str, port: int = 443, timeout: float = 10.0) -> bytes:
    """HTTPS GET via raw SSL socket."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with ctx.wrap_socket(socket.socket(), server_hostname=host) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Accept: */*\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        sock.sendall(request)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


def _decode_chunked(raw: bytes) -> bytes:
    """Decode HTTP chunked transfer encoding."""
    text = raw.decode("latin-1")
    header_end = text.find("\r\n\r\n")
    if header_end >= 0:
        text = text[header_end + 4:]
    else:
        return raw
    body_parts = []
    while text:
        crlf = text.find("\r\n")
        if crlf < 0:
            break
        size_hex = text[:crlf].strip()
        try:
            size = int(size_hex, 16)
        except ValueError:
            break
        if size == 0:
            break
        data_start = crlf + 2
        data_end = data_start + size
        body_parts.append(text[data_start:data_end].encode("latin-1"))
        text = text[data_end + 2:]
    return b"".join(body_parts)


def fetch_sina_kline_sync(stock_code: str, date_str: str = "") -> tuple[str, list[dict]]:
    """Fetch daily K-line from Sina. Returns (code, rows)."""
    path = f"/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={stock_code}&scale=240&ma=no&datalen=1000"
    try:
        raw = _sina_http_get_raw("money.finance.sina.com.cn", path, timeout=8.0)
        body = _decode_chunked(raw)
        text = body.decode("gbk", errors="replace")
        data = json.loads(text)
        if not isinstance(data, list) or not data:
            return stock_code, []
        rows = []
        for item in reversed(data):
            day = item.get("day", "")
            if date_str and day == date_str:
                rows.append({
                    "trade_date": day,
                    "open": float(item.get("open", 0)),
                    "close": float(item.get("close", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "volume": int(float(item.get("volume", 0))),
                    "amount": 0.0,
                })
                break
            elif not date_str:
                rows.append({
                    "trade_date": day,
                    "open": float(item.get("open", 0)),
                    "close": float(item.get("close", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "volume": int(float(item.get("volume", 0))),
                    "amount": 0.0,
                })
        return stock_code, rows
    except Exception as e:
        logger.warning(f"Sina kline failed for {stock_code}: {e}")
        return stock_code, []


# ── Stock List ─────────────────────────────────────────────────────────────────

def is_regular_a_share(code: str) -> bool:
    """Check if code is a regular A-share (not B-share, ETF, fund, etc.)."""
    code = code.lower().strip()
    if code.startswith("sh6") or code.startswith("sh9"):  # 沪市主板+科创板+B股
        return True
    if code.startswith("sz0") or code.startswith("sz3") or code.startswith("sz2"):  # 深市主板+创业板+中小板
        return True
    return False


def get_all_a_share_codes() -> list[str]:
    """Fetch all A-share codes. Tries mootdx first, then Sina as fallback."""
    # Try mootdx first
    client = tdx_client()
    if client:
        try:
            # Get all A-share codes from mootdx
            df = client.finance('000001')  # Just a probe
            # Get market data
            from mootdx.consts import MARKET_SH, MARKET_SZ
            sh_stocks = client.stocks(market=MARKET_SH)
            sz_stocks = client.stocks(market=MARKET_SZ)
            codes = []
            for row in sh_stocks.itertuples():
                code = str(row.symbol)
                if code.startswith(('6', '9')):
                    codes.append(f"sh{code}")
            for row in sz_stocks.itertuples():
                code = str(row.symbol)
                if code.startswith(('0', '3', '2')):
                    codes.append(f"sz{code}")
            if codes:
                logger.info(f"Got {len(codes)} A-share codes from mootdx")
                return list(set(codes))
        except Exception as e:
            logger.warning(f"mootdx stock list failed: {e}")

    # Fallback: Sina stock list
    import urllib.request
    try:
        url = "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
        params = "page=1&num=5000&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=page"
        full_url = f"{url}?{params}"
        req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("gbk"))
        codes = []
        for item in data:
            code = item.get("code", "")
            name = item.get("name", "")
            if code and name:
                prefix = "sh" if code.startswith("6") else "sz"
                full_code = f"{prefix}{code}"
                if is_regular_a_share(full_code):
                    codes.append(full_code)
        logger.info(f"Got {len(codes)} A-share codes from Sina")
        return list(set(codes))
    except Exception as e:
        logger.warning(f"Stock list fetch failed: {e}")
        return []


# ── Akshare Fallback ──────────────────────────────────────────────────────────

def _akshare_fallback_kline(code: str, date_str: str) -> list[dict]:
    """Akshare fallback for K-line data."""
    try:
        import akshare as ak
        pure_code = code[2:] if code[:2] in ("sh", "sz", "bj") else code
        df = ak.stock_zh_a_hist(symbol=pure_code, period="daily", adjust="")
        if df is None or df.empty:
            return []
        rows = []
        for _, row in df.iterrows():
            date = str(row["日期"])[:10]
            if date == date_str:
                rows.append({
                    "trade_date": date,
                    "open": float(row["开盘"]),
                    "close": float(row["收盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "volume": int(row["成交量"]),
                    "amount": float(row.get("成交额", 0)),
                })
        return rows
    except Exception as e:
        logger.warning(f"Akshare fallback failed for {code}: {e}")
        return []


# ── Priority Source Selection ─────────────────────────────────────────────────

def get_daily_kline(code: str, date_str: str = "") -> tuple[str, list[dict], str]:
    """
    Fetch daily K-line for one stock with priority routing.
    Returns (code, rows, source).

    Priority (per a-stock-data V3.6.1, 实测可用性 2026-08-14):
      mootdx(通达信,不可用) → Tencent qfq(前复权) → Sina(不复权) → Baidu(带MA) → Akshare
    全部 HTTP 源强制直连（不走系统代理）；东财因 IP 风控不稳定未列入主链路。
    """
    # 1. Try mootdx (TCP, fastest when available)
    src_code, rows = fetch_mootdx_kline_sync(code, date_str)
    if rows:
        return src_code, rows, "mootdx"

    # 2. Tencent qfq 前复权日K（a-stock-data 推荐，不封 IP，稳定直连）
    src_code, rows = fetch_tencent_kline_sync(code, date_str)
    if rows:
        return src_code, rows, "tencent"

    # 3. Sina 不复权日K（全量 1000 根）
    src_code, rows = fetch_sina_kline_sync(code, date_str)
    if rows:
        return src_code, rows, "sina"

    # 4. Baidu 带 MA 日K（裸代码才返回数据，全量返回）
    baidu_data = fetch_baidu_kline_sync(code)
    if baidu_data and baidu_data.get("rows"):
        if date_str:
            for row in baidu_data["rows"]:
                if row["date"] == date_str:
                    return code, [{
                        "trade_date": row["date"],
                        "open": row["open"],
                        "close": row["close"],
                        "high": row["high"],
                        "low": row["low"],
                        "volume": int(row["volume"]),
                        "amount": row["amount"],
                    }], "baidu"
        else:
            parsed = [{
                "trade_date": row["date"],
                "open": row["open"],
                "close": row["close"],
                "high": row["high"],
                "low": row["low"],
                "volume": int(row["volume"]),
                "amount": row["amount"],
            } for row in baidu_data["rows"]]
            if parsed:
                return code, parsed, "baidu"

    # 5. Akshare fallback
    if date_str:
        rows = _akshare_fallback_kline(code, date_str)
        if rows:
            return code, rows, "akshare"

    return code, [], "none"


def get_realtime_quotes(codes: list[str]) -> dict[str, dict]:
    """
    Fetch realtime quotes with fallback.
    Priority: Tencent (HTTP, stable)
    """
    return fetch_tencent_quotes_sync(codes)


# ── Utility ───────────────────────────────────────────────────────────────────

def normalize_code(code: str) -> str:
    """Normalize stock code to sh/sz prefix format."""
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")):
        return code
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"
