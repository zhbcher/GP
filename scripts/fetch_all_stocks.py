#!/usr/bin/env python3
"""
拉取 A 股主板非 ST 股票全历史 K 线数据到本地 SQLite。

数据源: 腾讯财经接口 (web.ifzq.gtimg.cn)
拉取范围: 3004 只主板非 ST 股票，全历史
目标: ~1900 万条 K 线
"""

import json, os, sys, time, sqlite3, math
import requests as _requests

# Bypass proxy
os.environ['no_proxy'] = '*'; os.environ['NO_PROXY'] = '*'
_orig = _requests.Session.__init__
def _patched(self, *a, **k):
    _orig(self, *a, **k); self.trust_env = False; self.proxies = {'http': None, 'https': None}
_requests.Session.__init__ = _patched

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
BATCH_SIZE = 100  # 每批提交
REQUEST_DELAY = 0.5  # 接口间隔（秒）
RETRY_DELAY = 5  # 重试间隔

# 主板非 ST 代码前缀
MAIN_BOARD_PREFIXES = ['600', '601', '603', '605', '000', '001', '002']

def get_all_stocks():
    """获取 A 股全市场股票列表，筛选主板非 ST"""
    import akshare as ak
    df = ak.stock_info_a_code_name()
    result = []
    for _, r in df.iterrows():
        code = r['code']
        name = r['name']
        prefix = code[:3]
        if prefix not in MAIN_BOARD_PREFIXES:
            continue
        if 'ST' in name.upper() or '退' in name:
            continue
        market = 'sh' if prefix in ['600', '601', '603', '605'] else 'sz'
        result.append((code, name, market))
    return result

def fetch_kline(stock_code, market):
    """从腾讯财经拉取全历史 K 线"""
    # 腾讯格式: sh600519 或 sz000001
    symbol = f"{market}{stock_code}"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},day,,,10000,qfq"
    try:
        r = _requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get('code') != 0:
            return None
        # 尝试获取 K 线数据
        stock_data = data.get('data', {}).get(symbol, {})
        # 优先取复权数据
        klines = stock_data.get('qfqday', []) or stock_data.get('day', [])
        if not klines:
            return None
        return klines
    except Exception as e:
        return None

def parse_kline(kline):
    """解析腾讯 K 线格式: [date, open, close, high, low, volume]"""
    # 注意腾讯格式: [date, open, close, high, low, volume]
    # 但有时顺序不同，需要根据字段判断
    try:
        if len(kline) >= 6:
            date = str(kline[0])
            open_p = float(kline[1])
            close = float(kline[2])
            high = float(kline[3])
            low = float(kline[4])
            vol = float(kline[5])
            return (date, open_p, close, high, low, vol)
    except (ValueError, IndexError):
        pass
    return None

def init_db():
    """确保数据库表存在"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS kline_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code VARCHAR(20) NOT NULL,
            trade_date VARCHAR(10) NOT NULL,
            open FLOAT NOT NULL,
            high FLOAT NOT NULL,
            low FLOAT NOT NULL,
            close FLOAT NOT NULL,
            volume BIGINT NOT NULL,
            amount FLOAT
        )
    """)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_kline_code_date
        ON kline_data (stock_code, trade_date)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS ix_kline_data_stock_code
        ON kline_data (stock_code)
    """)
    conn.commit()
    return conn

def main():
    print("获取 A 股主板非 ST 股票列表...")
    stocks = get_all_stocks()
    print(f"总主板非 ST 股票: {len(stocks)}")

    # 检查已有数据
    conn = init_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data")
    existing = {r[0] for r in cur.fetchall()}
    print(f"已有数据: {len(existing)} 只股票")

    # 需要拉取的股票
    to_fetch = []
    for code, name, market in stocks:
        sc = f"{market}{code}"
        if sc in existing:
            continue
        to_fetch.append((code, name, market, sc))

    print(f"需要拉取: {len(to_fetch)} 只股票")
    if not to_fetch:
        print("所有股票数据已齐全！")
        return

    total = len(to_fetch)
    batch = []
    success = 0
    failed = 0
    total_rows = 0
    start_time = time.time()

    for idx, (code, name, market, sc) in enumerate(to_fetch):
        if idx % 10 == 0:
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            eta = (total - idx - 1) / rate if rate > 0 else 0
            print(f"  [{idx+1}/{total}] {code} {name} | 已拉取{success}只/{failed}失败 | "
                  f"进度{(idx+1)/total*100:.1f}% | 速率{rate:.1f}只/分 | 预计剩余{eta/60:.0f}分钟")

        klines = fetch_kline(code, market)
        if klines is None:
            failed += 1
            time.sleep(REQUEST_DELAY)
            continue

        rows_inserted = 0
        for k in klines:
            parsed = parse_kline(k)
            if parsed is None:
                continue
            date, open_p, close, high, low, vol = parsed
            batch.append((sc, date, open_p, high, low, close, vol, 0.0))
            rows_inserted += 1

        if rows_inserted > 0:
            success += 1
            total_rows += rows_inserted

        # 批量写入
        if len(batch) >= BATCH_SIZE * 100:  # 每 10000 条提交一次
            _write_batch(conn, batch)
            batch = []

        time.sleep(REQUEST_DELAY)

    # 写入剩余数据
    if batch:
        _write_batch(conn, batch)

    elapsed = time.time() - start_time
    print(f"\n完成！")
    print(f"  成功: {success} 只股票")
    print(f"  失败: {failed} 只")
    print(f"  总数据行: {total_rows}")
    print(f"  耗时: {elapsed/60:.1f} 分钟")
    print(f"  平均速率: {total_rows/elapsed:.0f} 行/秒")

    conn.close()

def _write_batch(conn, batch):
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT OR IGNORE INTO kline_data (stock_code, trade_date, open, high, low, close, volume, amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            batch
        )
        conn.commit()
    except Exception as e:
        print(f"  DB write error: {e}")
        conn.rollback()
    batch.clear()

if __name__ == "__main__":
    main()