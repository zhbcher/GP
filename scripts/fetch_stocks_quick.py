#!/usr/bin/env python3
"""拉取A股主板非ST全历史K线（百度接口，不走代理，HTTP直连）"""
import os, sys, time, sqlite3, json
os.environ['no_proxy']='*'; os.environ['NO_PROXY']='*'
import requests as _r
_orig = _r.Session.__init__
def _p(self, *a, **k):
    _orig(self, *a, **k); self.trust_env=False; self.proxies={'http':None,'https':None}
_r.Session.__init__ = _p

DB = "/Users/zhoubo/GP/data/stock.db"
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS kline_data (id INTEGER PRIMARY KEY AUTOINCREMENT, stock_code VARCHAR(20) NOT NULL, trade_date VARCHAR(10) NOT NULL, open FLOAT NOT NULL, high FLOAT NOT NULL, low FLOAT NOT NULL, close FLOAT NOT NULL, volume BIGINT NOT NULL, amount FLOAT)")
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_kline_code_date ON kline_data (stock_code, trade_date)")
conn.commit()

cur.execute("SELECT DISTINCT stock_code FROM kline_data")
existing = {r[0] for r in cur.fetchall()}
print(f"已有: {len(existing)} 只股票")

import akshare as ak
df = ak.stock_info_a_code_name()
MAIN = {'600','601','603','605','000','001','002'}
stocks = [(r['code'],r['name'], 'sh' if r['code'][:3] in MAIN else 'sz')
          for _, r in df.iterrows()
          if r['code'][:3] in MAIN and 'ST' not in r['name'].upper() and '退' not in r['name']]
print(f"主板非ST: {len(stocks)} 只, 需拉取: {len(stocks)-len(existing)} 只")

BAIDU_URL = "https://finance.pae.baidu.com/selfselect/getstockquotation"
BAIDU_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/vnd.finance-web.v1+json',
    'Origin': 'https://gushitong.baidu.com',
    'Referer': 'https://gushitong.baidu.com/',
}

def fetch_stock(code, market):
    """拉取一只股票的全历史K线，返回 rows 列表"""
    sc = f"{market}{code}"
    all_rows = {}
    # 分两段拉取：2010-01-01 至今 + 更早数据
    for start_time in ['', '2010-01-01', '2000-01-01', '1995-01-01']:
        params = {'all':'1','isIndex':'false','isBk':'false','isBlock':'false',
                  'isFutures':'false','isStock':'true','newFormat':'1',
                  'group':'quotation_kline_ab','finClientType':'pc',
                  'code':code,'start_time':start_time,'ktype':'1'}
        try:
            r = _r.get(BAIDU_URL, params=params, headers=BAIDU_HEADERS, timeout=20)
            d = r.json()
            md = d.get('Result',{}).get('newMarketData',{})
            keys = md.get('keys',[])
            rows = [x.split(',') for x in md.get('marketData','').split(';') if x]
            # keys: timestamp, time, open, close, volume, high, low, amount, range, ratio
            for row in rows:
                if len(row) >= 7:
                    all_rows[row[1]] = (row[1], float(row[2]), float(row[5]), float(row[6]), float(row[3]), int(float(row[4])), float(row[7]) if len(row) > 7 else 0.0)
            if len(rows) < 2000:
                break  # 已到最早期
        except Exception as e:
            break
    return list(all_rows.values())

t0 = time.time()
batch = []
ok = fail = 0
for idx, (code, name, market) in enumerate(stocks):
    sc = f"{market}{code}"
    if sc in existing:
        continue
    if ok % 20 == 0:
        elapsed = time.time() - t0
        rate = ok / elapsed if elapsed > 0 else 0
        left = len(stocks) - len(existing) - ok
        eta = left / rate if rate > 0 else 999
        print(f"  [{ok}ok/{fail}fail] {code} {name} | {rate:.1f}/s | ETA={eta/60:.0f}min", flush=True)
    try:
        rows = fetch_stock(code, market)
        if rows:
            batch.extend([(sc, r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows])
            ok += 1
        else:
            fail += 1
    except Exception as e:
        fail += 1

    if len(batch) >= 20000:
        cur.executemany("INSERT OR IGNORE INTO kline_data (stock_code,trade_date,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?)", batch)
        conn.commit()
        batch = []
    time.sleep(0.3)

if batch:
    cur.executemany("INSERT OR IGNORE INTO kline_data (stock_code,trade_date,open,high,low,close,volume,amount) VALUES (?,?,?,?,?,?,?,?)", batch)
    conn.commit()

conn.close()
t = time.time() - t0
print(f"\n完成! OK={ok} FAIL={fail} 耗时={t/60:.1f}min 速率={ok/t:.1f}/s")