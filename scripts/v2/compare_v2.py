#!/usr/bin/env python3
"""
GP 选股方案 v2 — 与现有超跌反弹方案（run_signals.py 逻辑）同区间对比

策略 A（现有方案）：9 个超跌条件（N日跌X% 且 连续阴跌M天）任一触发 → 买入
策略 B（v2 方案）：综合得分 Top 层（层8，80-90分位）→ 买入
两者同区间（20 日持有）回测对比：年化 / 累计 / 回撤 / Sharpe / 月胜率 / 平均持仓数

用法:
  python compare_v2.py --start 2018-01-01
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from factors_v2 import compute_factors_for_stock
from scorer_v2 import composite_score
from backtest_v2 import load_factors, net_value

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
FREQ = 20
COST = 0.001
LAYER8 = 8

# 现有方案 9 个基础超跌条件（来自 scripts/factors.py BASE_FACTORS）
BASE_FACTORS = [
    {"days": 5, "drop_pct": 6, "consec": 3},
    {"days": 5, "drop_pct": 8, "consec": 4},
    {"days": 7, "drop_pct": 8, "consec": 5},
    {"days": 7, "drop_pct": 10, "consec": 5},
    {"days": 10, "drop_pct": 10, "consec": 7},
    {"days": 10, "drop_pct": 12, "consec": 7},
    {"days": 10, "drop_pct": 15, "consec": 8},
    {"days": 15, "drop_pct": 15, "consec": 10},
    {"days": 20, "drop_pct": 20, "consec": 14},
]


def oversold_trigger(closes: np.ndarray, days: int, drop_pct: int, consec: int) -> np.ndarray:
    """现有方案超跌信号：返回布尔数组（当日是否触发）。"""
    n = len(closes)
    out = np.zeros(n, dtype=bool)
    for i in range(days, n):
        if closes[i - days] <= 0:
            continue
        ret = closes[i] / closes[i - days] - 1.0
        if ret >= -drop_pct / 100.0:
            continue
        down = 0
        for j in range(i, i - days, -1):
            if j <= 0:
                break
            if closes[j] < closes[j - 1]:
                down += 1
            else:
                break
        if down >= consec:
            out[i] = True
    return out


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2018-01-01")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    print(f"[init] 股票 {len(codes)} 只, 起始 {args.start}")

    print("[1/3] 加载数据 + 计算 v2 因子...")
    panel = load_factors(conn, codes, args.start)
    # 现有信号需要完整 closes 序列（含起始前数据），单独加载原始序列
    raw = {}
    for i, code in enumerate(codes):
        df = pd.read_sql("SELECT trade_date, close FROM kline_data WHERE stock_code=? ORDER BY trade_date",
                         conn, params=(code,))
        raw[code] = df
        if (i + 1) % 2000 == 0:
            print(f"  [raw] {i + 1}/{len(codes)}")
    conn.close()

    print("[2/3] 计算 v2 得分 + 现有超跌信号...")
    fwd = []
    for code, g in panel.groupby(level="stock_code"):
        fwd.append(g["close"].shift(-FREQ) / g["close"] - 1.0)
    panel["fwd_5"] = pd.concat(fwd).sort_index()
    panel = panel[panel["fwd_5"].notna()]
    score = composite_score(panel)

    # 现有信号：构建 date->set(signal stocks)，并计算每只股票信号日的未来收益
    dates_all = sorted(panel.index.get_level_values("date").unique())
    date_set = set(dates_all)
    sig_fwd = {}  # (date, code) -> fwd_20
    for code, df in raw.items():
        df = df[df["trade_date"].isin(date_set)]
        closes = df["close"].to_numpy(dtype=float)
        if len(closes) < 80:
            continue
        trig = np.zeros(len(closes), dtype=bool)
        for bf in BASE_FACTORS:
            trig |= oversold_trigger(closes, bf["days"], bf["drop_pct"], bf["consec"])
        f = np.full(len(closes), np.nan)
        f[:len(closes) - FREQ] = closes[FREQ:] / closes[:len(closes) - FREQ] - 1.0
        for i in range(len(closes)):
            if trig[i]:
                sig_fwd[(df.iloc[i]["trade_date"], code)] = f[i]

    # 策略 A：每期持仓 = 当日触发信号的股票（等权未来20日收益）
    rebalance = dates_all[::FREQ]
    strat_a = []
    for d in rebalance:
        fwds = [v for (dd, _), v in sig_fwd.items() if dd == d and np.isfinite(v)]
        if len(fwds) >= 5:
            strat_a.append(np.mean(fwds) - COST)

    # 策略 B：层 8 组合
    strat_b = []
    for d in rebalance:
        cross = panel.xs(d, level="date")
        tmp = pd.DataFrame({"score": score.xs(d, level="date"), "fwd": cross["fwd_5"],
                            "close": cross["close"], "amt": cross["amt_60"]}).dropna()
        tmp = tmp[(tmp["close"] >= 3.0) & (tmp["amt"] >= 3e7)]
        if len(tmp) < 50:
            continue
        q = pd.qcut(tmp["score"].rank(method="first"), 10, labels=False)
        layer8 = tmp[q == LAYER8]
        if len(layer8) >= 10:
            strat_b.append(layer8["fwd"].mean() - COST)

    print("[3/3] 对比...")
    _, ma = net_value(strat_a, 0)
    _, mb = net_value(strat_b, 0)
    # 基准
    mkt = panel.groupby(level="date")["fwd_5"].mean().reindex(rebalance).dropna()
    _, mm = net_value(mkt.tolist(), 0)

    print(f"\n{'=' * 66}\n  同区间对比（{args.start} ~ 今, 20日调仓, 成本0.1%）\n{'=' * 66}")
    print(f"{'策略':<24}{'年化':>8}{'累计':>9}{'Sharpe':>8}{'回撤':>9}{'期数':>6}")
    print(f"  A 现有超跌信号     {ma['ann']:>7.1%}{ma['total']:>8.1%}{ma['sharpe']:>8.2f}{ma['mdd']:>8.1%}{ma['periods']:>6}")
    print(f"  B v2 层8(80-90分位) {mb['ann']:>7.1%}{mb['total']:>8.1%}{mb['sharpe']:>8.2f}{mb['mdd']:>8.1%}{mb['periods']:>6}")
    print(f"  基准 全市场等权     {mm['ann']:>7.1%}{mm['total']:>8.1%}{mm['sharpe']:>8.2f}{mm['mdd']:>8.1%}{mm['periods']:>6}")
    print(f"\n  信号触发期数: A={len(strat_a)}, B={len(strat_b)}")
    print(f"\n  总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
