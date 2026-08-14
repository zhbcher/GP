"""
备用分时数据源 — 使用东方财富HTTP接口
"""
import logging
import ssl
import socket
import json
from typing import Optional

logger = logging.getLogger(__name__)


class EastmoneyMinuteSource:
    """东方财富分时数据接口（HTTP）"""
    
    @staticmethod
    async def fetch_minute(code: str) -> dict:
        """
        获取今日分时数据
        返回: {prev_close, data: [{time, price, avg_price, volume}]}
        """
        # 转换股票代码格式
        pure_code = code[2:] if code[:2] in ("sh", "sz", "bj") else code
        market = "1" if pure_code.startswith("6") else "0"  # 1=沪, 0=深
        
        try:
            # 使用原始SSL socket绕过TLS指纹检测
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            path = (
                f"/api/qt/stock/trends/Get"
                f"?secid={market}.{pure_code}"
                f"&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
                f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
                f"&ut=fa5fd1943c7b386f172d6893dbbd1d0c"
                f"&iscr=0&iscca=0&fltt=2"
            )
            
            raw = await _http_get_raw_async("push2.eastmoney.com", path, timeout=8.0)
            if not raw:
                return {"prev_close": 0, "data": []}
            
            # 解析响应
            text = raw.decode("utf-8", "replace")
            payload = json.loads(text)
            
            if not payload.get("data"):
                return {"prev_close": 0, "data": []}
            
            trends = payload["data"].get("trends", [])
            basic = payload["data"].get("basic", {})
            
            # 获取昨收价
            prev_close = float(basic.get("close", 0)) if basic else 0
            
            # 解析分时数据
            data = []
            for item in trends:
                parts = item.split(",")
                if len(parts) < 4:
                    continue
                
                time_str = parts[0]  # "2026-08-11 09:35:00"
                price = float(parts[1])
                avg_price = float(parts[2])
                volume = int(parts[3])
                
                # 提取时间部分
                time_part = time_str.split(" ")[-1] if " " in time_str else time_str
                
                data.append({
                    "time": time_part,
                    "price": price,
                    "avg_price": avg_price,
                    "volume": volume,
                })
            
            return {
                "prev_close": prev_close,
                "data": data,
                "count": len(data),
            }
            
        except Exception as e:
            logger.warning(f"东方财富分时数据获取失败 {code}: {e}")
            return {"prev_close": 0, "data": []}


async def _http_get_raw_async(host: str, path: str, port: int = 443, timeout: float = 10.0) -> Optional[bytes]:
    """Async HTTPS GET via raw SSL socket."""
    import asyncio
    
    def _fetch():
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
    
    try:
        return await asyncio.get_event_loop().run_in_executor(None, _fetch)
    except Exception as e:
        logger.warning(f"HTTP request failed: {e}")
        return None
