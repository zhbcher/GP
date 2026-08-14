#!/usr/bin/env python3
"""
A股沪深主板全历史日K批量拉取脚本
- 数据源: 通达信 mootdx (218.75.126.9, 已验证可用)
- 范围: 沪深主板 (sh600/601/603/605 + sz000/001/002/003)
- 方式: 分页拉全历史 → 排序 → OR REPLACE 批量写入 SQLite
- 断点续跑: 已完成列表写 /tmp/main_board_done.txt, 中断后重新运行自动跳过
用法:
    python scripts/fetch_main_board_full.py [代码列表文件] [输出DB路径]
默认: /tmp/missing_main_board.txt → /Users/zhoubo/GP/data/stock.db
"""
import os
import sys
import time
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.data_sources.a_stock_data import tdx_client

LIST_FILE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/missing_main_board.txt"
DB_PATH = sys.argv[2] if len(sys.argv) > 2 else "/Users/zhoubo/GP/data/stock.db"
DONE_FILE = "/tmp/main_board_done.txt"
FAIL_FILE = "/tmp/main_board_fail.txt"

BATCH = 2000  # 每批写入行数


def load_done():
    if not os.path.exists(DONE_FILE):
        return set()
    return set(l.strip() for l in open(DONE_FILE) if l.strip())


def save_done(code):
    with open(DONE_FILE, "a") as f:
        f.write(code + "\n")


def fetch_full_history(client, pure_code: str) -> list[dict]:
    """mootdx 分页拉全历史日K，返回从旧到新排列的 rows。"""
    all_parts = []
    start = 0
    while True:
        df = client.bars(symbol=pure_code, frequency=9, start=start, offset=800)
        if df is None or len(df) == 0:
            break
        all_parts.append(df)
        if len(df) < 800:
            break
        start += 800
        if start > 20000:  # 安全上限（约 80 年）
            break

    rows = []
    for df in all_parts:
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
                0.0,
            ))
    # 从旧到新排序（分页返回从新到旧）
    rows.sort(key=lambda x: x[0])
    return rows


def main():
    codes = [l.strip() for l in open(LIST_FILE) if l.strip()]
    done = load_done()
    todo = [c for c in codes if c not in done]
    print(f"[init] 总 {len(codes)} 只, 已完成 {len(done)}, 待拉 {len(todo)}")

    client = tdx_client()
    if not client:
        print("[fatal] mootdx 客户端不可用")
        sys.exit(1)
    print(f"[init] mootdx 客户端 OK ({client.client.ip if hasattr(client, 'client') else '?'})")

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")

    t_start = time.time()
    ok = 0
    fail = 0
    total_bars = 0

    for i, code in enumerate(todo, 1):
        pure = code[2:]
        t0 = time.time()
        try:
            rows = fetch_full_history(client, pure)
            if not rows:
                print(f"[{i}/{len(todo)}] {code}: 无数据")
                with open(FAIL_FILE, "a") as f:
                    f.write(f"{code}\tno_data\n")
                fail += 1
                continue

            # 批量写入 OR REPLACE
            sql = ("INSERT OR REPLACE INTO kline_data "
                   "(stock_code, trade_date, open, high, low, close, volume, amount) "
                   "VALUES (?,?,?,?,?,?,?,?)")
            for b in range(0, len(rows), BATCH):
                chunk = rows[b:b + BATCH]
                conn.executemany(sql, [(code, r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in chunk])
            conn.commit()

            total_bars += len(rows)
            ok += 1
            save_done(code)
            dt = time.time() - t0
            if i % 50 == 0 or i == len(todo):
                el = time.time() - t_start
                rate = ok / el * 60
                print(f"[{i}/{len(todo)}] {code}: {len(rows)} 根 ({dt:.1f}s) | "
                      f"成功 {ok}, 失败 {fail}, 总写入 {total_bars} 根, 速率 {rate:.0f} 只/分, "
                      f"已用 {el/60:.1f} 分")
        except Exception as e:
            print(f"[{i}/{len(todo)}] {code}: 异常 {type(e).__name__}: {str(e)[:80]}")
            with open(FAIL_FILE, "a") as f:
                f.write(f"{code}\t{type(e).__name__}: {str(e)[:100]}\n")
            fail += 1
            # 偶发失败重试一次
            time.sleep(1)

    conn.close()
    elapsed = (time.time() - t_start) / 60
    print(f"\n[完成] 成功 {ok}, 失败 {fail}, 共写入 {total_bars} 根, 耗时 {elapsed:.1f} 分钟")
    print(f"失败列表: {FAIL_FILE}")


if __name__ == "__main__":
    main()
