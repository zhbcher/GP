#!/usr/bin/env python3
"""
修复 kline_data 中 amount=0（及 volume 单位错误）的存量数据。
- 找出所有 amount=0 的股票 → 用通达信(mootdx)分页拉全历史（含真实 amount/volume）
- 直接 INSERT OR REPLACE 覆盖（不经过 _normalize_volume，通达信 vol 已是"手"）
- 断点续跑：已完成列表落盘 /tmp/amount_fix_done.txt
用法:
    python scripts/fix_amount_full.py
"""
import os
import sys
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.data_sources.a_stock_data import tdx_client

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
DONE_FILE = "/tmp/amount_fix_done.txt"
BATCH = 2000
LIST_FILE = sys.argv[1] if len(sys.argv) > 1 else None  # 可选：指定股票列表（测试用）


def get_affected_stocks(conn) -> list[str]:
    if LIST_FILE:
        return [l.strip() for l in open(LIST_FILE) if l.strip()]
    cur = conn.execute("""
        SELECT DISTINCT stock_code FROM kline_data WHERE amount = 0
        ORDER BY stock_code
    """)
    return [r[0] for r in cur.fetchall()]


def fetch_full_history(client, pure_code: str) -> list[tuple]:
    """分页拉全历史日K，返回 (date, open, high, low, close, vol, amount) 从旧到新。"""
    parts = []
    start = 0
    while True:
        df = client.bars(symbol=pure_code, frequency=9, start=start, offset=800)
        if df is None or len(df) == 0:
            break
        parts.append(df)
        if len(df) < 800:
            break
        start += 800
        if start > 20000:
            break

    rows = []
    for df in parts:
        for _, r in df.iterrows():
            d = str(r.get("datetime", ""))[:10]
            if not d or d == "NaT":
                continue
            rows.append((
                d,
                float(r.get("open", 0)),
                float(r.get("high", 0)),
                float(r.get("low", 0)),
                float(r.get("close", 0)),
                int(float(r.get("vol", 0))),
                float(r.get("amount", 0) or 0),
            ))
    rows.sort(key=lambda x: x[0])
    return rows


def main():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")

    stocks = get_affected_stocks(conn)
    done = set()
    if os.path.exists(DONE_FILE):
        done = set(l.strip() for l in open(DONE_FILE) if l.strip())
    todo = [s for s in stocks if s not in done]
    print(f"[init] amount=0 涉及股票 {len(stocks)} 只, 已完成 {len(done)}, 待修 {len(todo)}")

    client = tdx_client()
    if not client:
        print("[fatal] mootdx 不可用")
        sys.exit(1)
    print(f"[init] mootdx OK ({client.client.ip if hasattr(client, 'client') else '?'})")

    sql = ("INSERT OR REPLACE INTO kline_data "
           "(stock_code, trade_date, open, high, low, close, volume, amount) "
           "VALUES (?,?,?,?,?,?,?,?)")

    t0 = time.time()
    ok = fail = fixed_rows = 0
    for i, code in enumerate(todo, 1):
        pure = code[2:]
        try:
            rows = fetch_full_history(client, pure)
            if not rows:
                fail += 1
                continue
            for b in range(0, len(rows), BATCH):
                chunk = rows[b:b + BATCH]
                conn.executemany(sql, [(code, r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in chunk])
            conn.commit()
            ok += 1
            fixed_rows += len(rows)
            with open(DONE_FILE, "a") as f:
                f.write(code + "\n")
            if i % 100 == 0 or i == len(todo):
                el = time.time() - t0
                print(f"[{i}/{len(todo)}] {code}: {len(rows)} 根 | 成功 {ok}, 失败 {fail}, "
                      f"共覆盖 {fixed_rows:,} 根, 速率 {ok/el*60:.0f} 只/分, 已用 {el/60:.1f} 分")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(todo)}] {code}: {type(e).__name__}: {str(e)[:70]}")
            time.sleep(1)

    conn.close()
    print(f"\n[完成] 成功 {ok}, 失败 {fail}, 共覆盖 {fixed_rows:,} 根, 耗时 {(time.time()-t0)/60:.1f} 分")


if __name__ == "__main__":
    main()
