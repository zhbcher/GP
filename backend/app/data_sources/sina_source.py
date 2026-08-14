"""
Sina Finance kline fetcher — raw SSL socket with chunked transfer decoding.

Sina uses chunked Transfer-Encoding and GBK charset, unlike eastmoney's direct JSON.
"""
import json
import logging
import ssl
import socket
from typing import Optional

logger = logging.getLogger(__name__)


def _http_get_raw(host: str, path: str, port: int = 443, timeout: float = 10.0) -> bytes:
    """Make HTTPS GET via raw SSL socket, return raw body bytes."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with ctx.wrap_socket(
        socket.socket(),
        server_hostname=host,
    ) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n"
            f"Accept: */*\r\n"
            f"Connection: close\r\n"
            f"\r\n"
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
    """Decode HTTP chunked transfer encoding, return raw body bytes."""
    text = raw.decode("latin-1")  # safe for any byte
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
        text = text[data_end + 2:]  # skip \r\n after chunk

    return b"".join(body_parts)


def _parse_sina_klines(raw_body: bytes) -> list[dict]:
    """Parse Sina JSON (GBK-encoded) into normalized row dicts."""
    try:
        text = raw_body.decode("gbk", errors="replace")
    except Exception:
        text = raw_body.decode("utf-8", errors="replace")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    rows = []
    for item in data:
        day = item.get("day", "")
        close_s = item.get("close", "0")
        open_s = item.get("open", "0")
        high_s = item.get("high", "0")
        low_s = item.get("low", "0")
        vol_s = item.get("volume", "0")
        try:
            rows.append({
                "trade_date": day,
                "open": float(open_s),
                "close": float(close_s),
                "high": float(high_s),
                "low": float(low_s),
                "volume": int(float(vol_s)),
                "amount": 0.0,  # Sina doesn't provide amount in this endpoint
            })
        except (ValueError, TypeError):
            continue
    return rows


def fetch_sina_kline_sync(stock_code: str, date_str: str, timeout: float = 8.0) -> tuple[str, list[dict]]:
    """Fetch daily kline for one stock from Sina. Returns (code, rows)."""
    path = f"/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={stock_code}&scale=240&ma=no&datalen=1"
    raw = _http_get_raw("money.finance.sina.com.cn", path, timeout=timeout)
    body = _decode_chunked(raw)
    rows = _parse_sina_klines(body)
    return stock_code, rows
