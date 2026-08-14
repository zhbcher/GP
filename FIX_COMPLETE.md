# 分时图修复报告

## 问题描述
分时图无法显示，API返回 `prev_close: 0, count: 0`

## 根本原因

1. **quotes接口在非交易时间返回空数据**
   - mootdx的`quotes()`接口只在交易时间返回数据
   - 非交易时间无法获取`last_close`（昨收价）
   
2. **tdx_client()的bestip选择延迟**
   - 每次创建客户端都执行服务器速度测试（约20秒）
   - 原始30秒超时在某些网络环境下不够

## 修复方案

### 1. 添加数据库fallback（mootdx_source.py）

```python
# Fallback: try database if quotes unavailable (non-trading hours)
if prev_close == 0.0:
    try:
        import sqlite3
        import os
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "stock.db")
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT close FROM kline_data WHERE stock_code = ? ORDER BY trade_date DESC LIMIT 1", (code,))
            row = cursor.fetchone()
            if row:
                prev_close = float(row[0])
            conn.close()
    except Exception as e:
        logger.debug(f"DB fallback for prev_close failed: {e}")
```

### 2. 跳过bestip选择（mootdx_source.py）

```python
def _get_client(self):
    """获取mootdx客户端，使用缓存避免重复创建"""
    if self._client is None:
        # 直接使用第一个已知可用的服务器，跳过bestip选择
        from mootdx.quotes import Quotes
        self._client = Quotes.factory(market='std', server=('119.97.185.59', 7709))
    return self._client
```

### 3. 增加超时时间

```python
timeout=45.0  # 从30秒增加到45秒
```

## 测试结果

```bash
# API测试
curl "http://localhost:8000/api/stock/sh600188/timeline"
# 返回: {"code":"sh600188","name":"兖矿能源","prev_close":21.33,"data":[...240条...],"count":240}
```

## 服务状态

- 前端: http://localhost:5173/ ✅
- 后端: http://localhost:8000/ ✅
- API: prev_close=21.33, count=240 ✅

## 修改文件

- `/Users/zhoubo/GP/backend/app/data_sources/mootdx_source.py`
