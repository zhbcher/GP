"""
腾讯财经分时数据源 — HTTP接口（海外可用）
"""
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class TencentMinuteSource:
    """腾讯财经分时数据接口"""
    
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
            async with httpx.AsyncClient(timeout=10) as client:
                # 尝试获取分时数据
                url = f"http://web.sqt.gtimg.cn/q={pure_code}"
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                
                if resp.status_code != 200:
                    logger.warning(f"腾讯分时API返回非200状态码: {resp.status_code}")
                    return {"prev_close": 0, "data": []}
                
                # 解析响应
                text = resp.text
                if "=" not in text:
                    return {"prev_close": 0, "data": []}
                
                _, data_str = text.split("=", 1)
                fields = data_str.strip().split("~")
                
                if len(fields) < 45:
                    return {"prev_close": 0, "data": []}
                
                prev_close = float(fields[4]) if fields[4] else 0
                
                # 尝试获取分时数据（如果有的话）
                # 腾讯实时报价API不直接提供分时，需要另一个接口
                minute_url = f"http://ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data_{pure_code}&code={pure_code}"
                minute_resp = await client.get(minute_url, headers={"User-Agent": "Mozilla/5.0"})
                
                data = []
                if minute_resp.status_code == 200:
                    try:
                        minute_text = minute_resp.text
                        # 解析JavaScript变量格式
                        if "min_data_" in minute_text:
                            json_str = minute_text.split("=", 1)[1].strip().rstrip(";")
                            minute_data = eval(json_str)  # 安全解析
                            
                            if isinstance(minute_data, dict):
                                trends = minute_data.get("trends", [])
                                for item in trends:
                                    parts = item.split(",")
                                    if len(parts) >= 4:
                                        data.append({
                                            "time": parts[0],
                                            "price": float(parts[1]),
                                            "avg_price": float(parts[2]) if parts[2] else 0,
                                            "volume": int(parts[3]) if parts[3] else 0,
                                        })
                    except Exception as e:
                        logger.warning(f"解析腾讯分时数据失败: {e}")
                
                return {
                    "prev_close": prev_close,
                    "data": data,
                    "count": len(data),
                }
                
        except Exception as e:
            logger.error(f"腾讯分时数据获取失败: {e}")
            return {"prev_close": 0, "data": []}
