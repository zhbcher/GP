#!/usr/bin/env python3
"""
GP 选股方案 v2 — 分年度回测报告

在 backtest_v2 基础上，输出 Top 层（层8+9，Top 20%）每年的收益表现，
逐年验证策略稳健性（排除单一市场年份驱动结论）。

用法:
  python yearly_report.py --start 2018-01-01
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
from backtest_v2 import load_factors, MIN_BARS

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
FREQ = 20
N_LAYERS = 10
COST = 0.001
TARGET_LAYERS = {8}     # 最优层（80-90 分位）


def yearly_returns(panel: pd.DataFrame, score: pd.Series) -> pd.DataFrame:
    """每期调仓日：Top20% 组合收益 + 基准收益（带日期）。"""
    dates = sorted(panel.index.get_level_values("date").unique())
    rebalance = dates[::FREQ]
    rows = []
    for d in rebalance:
        cross = panel.xs(d, level="date")
        tmp = pd.DataFrame({
            "score": score.xs(d, level="date"),
            "fwd": cross["fwd_5"],
            "close": cross["close"],
            "amt": cross["amt_60"],
        }).dropna()
        tmp = tmp[(tmp["close"] >= 3.0) & (tmp["amt"] >= 3e7)]
        if len(tmp) < 50:
            continue
        q = pd.qcut(tmp["score"].rank(method="first"), N_LAYERS, labels=False)
        tmp["layer"] = q
        top = tmp[tmp["layer"].isin(TARGET_LAYERS)]
        if len(top) < 10:
            continue
        rows.append({
            "date": d,
            "top_ret": top["fwd"].mean() - COST,
            "bench_ret": tmp["fwd"].mean() - COST,
            "n_top": len(top),
        })
    return pd.DataFrame(rows)


def main():
    global t0
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2018-01-01")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    print(f"[init] 股票 {len(codes)} 只, 起始 {args.start}")

    print("[1/3] 计算因子...")
    panel = load_factors(conn, codes, args.start)
    conn.close()
    fwd = []
    for code, g in panel.groupby(level="stock_code"):
        fwd.append(g["close"].shift(-FREQ) / g["close"] - 1.0)
    panel["fwd_5"] = pd.concat(fwd).sort_index()
    panel = panel[panel["fwd_5"].notna()]
    print(f"  面板 {panel.shape}, {time.time() - t0:.0f}s")

    print("[2/3] 综合得分...")
    score = composite_score(panel)

    print("[3/3] 分年度回测...")
    yr = yearly_returns(panel, score)
    yr["year"] = yr["date"].str[:4]

    print(f"\n{'=' * 72}\n  分年度表现（层8组合 vs 全市场等权, 单边成本 0.1%）\n{'=' * 72}")
    print(f"{'年份':<6}{'期数':>5}{'组合年化':>10}{'基准年化':>10}{'超额':>9}{'组合累计':>10}")
    all_rows = []
    for year, g in yr.groupby("year"):
        cum = (1 + g["top_ret"]).prod() - 1
        cum_b = (1 + g["bench_ret"]).prod() - 1
        n = len(g)
        ann = (1 + cum) ** (12 / n) - 1 if n > 0 else 0
        ann_b = (1 + cum_b) ** (12 / n) - 1 if n > 0 else 0
        print(f"{year:<6}{n:>5}{ann:>9.1%}{ann_b:>9.1%}{ann - ann_b:>+8.1%}{cum:>9.1%}")
        all_rows.append((year, n, ann, ann_b, cum))

    # 总览
    total_cum = (1 + yr["top_ret"]).prod() - 1
    total_cum_b = (1 + yr["bench_ret"]).prod() - 1
    n = len(yr)
    ann = (1 + total_cum) ** (12 / n) - 1
    ann_b = (1 + total_cum_b) ** (12 / n) - 1
    print(f"\n  全程: 组合年化 {ann:.1%}  基准年化 {ann_b:.1%}  累计 {total_cum:.1%} vs {total_cum_b:.1%}")

    # 年度胜率
    win_years = sum(1 for _, _, a, _, _ in all_rows if a > 0)
    print(f"  盈利年份: {win_years}/{len(all_rows)}")
    print(f"\n  总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
