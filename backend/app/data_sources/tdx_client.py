"""
Robust mootdx (Tongdaxin) client factory.

Adapted from simonlin1212/a-stock-data v3.6.0 `tdx_client()`:
  - Works around mootdx 0.11.x BESTIP.HQ empty-string bug (explicit server list)
  - Real-data validation per candidate server (TCP handshake alone is not enough:
    a bad server can accept the handshake but reply with a 2-byte empty body,
    silently returning empty DataFrames)
  - Fallback chain: explicit server list -> bestip speed-test -> bare factory
"""
import logging
import socket

logger = logging.getLogger(__name__)

# Verified-working backup servers (sorted by latency, a-stock-data 2026-06)
TDX_SERVERS = [
    ('119.97.185.59', 7709), ('124.70.133.119', 7709), ('116.205.183.150', 7709),
    ('123.60.73.44', 7709),  ('116.205.163.254', 7709), ('121.36.225.169', 7709),
    ('123.60.70.228', 7709), ('124.71.9.153', 7709),    ('110.41.147.114', 7709),
    ('124.71.187.122', 7709),
]


def _probe(ip: str, port: int, timeout: float = 2.0) -> bool:
    """TCP handshake probe (fast coarse filter). Handshake success != data works."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def _validate(client, market: str = 'std') -> bool:
    """Real-data validation: pull one actual K-line bar; a bad server can pass
    the TCP handshake yet return an empty body (silent empty table)."""
    if market != 'std':
        return True
    try:
        df = client.bars(symbol='000001', frequency=9, offset=1)
        return df is not None and not df.empty
    except Exception:
        return False


def tdx_client(market: str = 'std'):
    """Create a validated mootdx client.

    Chain:
      1) Walk TDX_SERVERS; probe then validate; take the first that returns data.
      2) Fall back to mootdx built-in bestip speed test (also validated).
      3) Fall back to bare factory (works when config already has a good BESTIP).
      4) Raise RuntimeError with a clear message instead of failing silently.
    """
    from mootdx.quotes import Quotes

    for ip, port in TDX_SERVERS:
        if not _probe(ip, port):
            continue
        try:
            c = Quotes.factory(market=market, server=(ip, port))
            if _validate(c, market):
                logger.info(f"tdx_client: using server {ip}:{port}")
                return c
        except Exception:
            continue  # handshake ok but data fetch crashed -> try next

    for kwargs in ({'bestip': True}, {}):  # fallback: bestip speed-test / bare factory
        try:
            c = Quotes.factory(market=market, **kwargs)
            if _validate(c, market):
                logger.info(f"tdx_client: fallback client ok (kwargs={kwargs})")
                return c
        except Exception:
            continue

    raise RuntimeError(
        "所有 mootdx 服务器均无法取到数据（TCP 可达但返回空 / 被 reset）。"
        "海外网络通常全部超时（TCP 7709），请走国内代理或更新 TDX_SERVERS 列表。"
    )
