"""
Eastmoney kline fetcher — uses raw SSL sockets to bypass TLS fingerprinting.

The eastmoney API (push2his.eastmoney.com) rejects requests from tools like
curl and httpx (TLS fingerprint blocking), but raw Python ssl.SSLObject works.
"""
import json
import logging
import ssl
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

# Reusable thread pool for SSL socket operations
_executor = ThreadPoolExecutor(max_workers=1)


def _http_get_raw(host: str, path: str, port: int = 443, timeout: float = 10.0) -> bytes:
    """Make an HTTPS GET request using raw SSL socket (bypasses TLS fingerprinting)."""
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
            f"User-Agent: Mozilla/5.0\r\n"
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


def _parse_kline_response(raw: bytes) -> list[dict]:
    """Extract kline data from eastmoney response body."""
    text = raw.decode("utf-8", "replace")
    body = text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in text else text
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []

    klines = (payload.get("data") or {}).get("klines") or []
    rows = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 7:
            continue
        rows.append({
            "trade_date": parts[0],
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": int(float(parts[5])),
            "amount": float(parts[6]),
        })
    return rows


def fetch_kline_single_sync(stock_code: str, date_str: str, timeout: float = 8.0) -> tuple[str, list[dict]]:
    """Synchronous fetch of one stock's daily kline. Returns (code, rows)."""
    pure = stock_code[2:]
    market = "1" if pure.startswith("6") else "0"
    path = (
        f"/api/qt/stock/kline/get"
        f"?fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0"
        f"&secid={market}.{pure}"
        f"&beg={date_str}&end={date_str}"
        f"&ut=7eea3edcaed734bea9cbfc24409ed989"
    )
    raw = _http_get_raw("push2his.eastmoney.com", path, timeout=timeout)
    rows = _parse_kline_response(raw)
    return stock_code, rows
