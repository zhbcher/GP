#!/usr/bin/env python3
"""
GP 选股方案 v2 — 市场状态动态因子 vs 静态反转 对比

静态：4 因子等权反向（当前 v2 方案）
动态：牛市切换 M1/M3 为动量正向，熊/震荡保持反转

用法:
  python backtest_dynamic.py --start 2018-01-01
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from scorer_v2 import composite_score, dynamic_score
from backtest_v2 import load_factors, net_value, market_regime

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
FREQ = 20
N_LAYERS = 10
COST = 0.001
LAYER8 = 8


def layer8_returns(panel: pd.DataFrame, score: pd.Series) -> list[float]:
    """层 8 组合周频收益序列。"""
    dates = sorted(panel.index.get_level_values("date").unique())
    rebalance = dates[::FREQ]
    rets = []
    for d in rebalance:
        cross = panel.xs(d, level="date")
        tmp = pd.DataFrame({"score": score.xs(d, level="date"), "fwd": cross["fwd_5"],
                            "close": cross["close"], "amt": cross["amt_60"]}).dropna()
        tmp = tmp[(tmp["close"] >= 3.0) & (tmp["amt"] >= 3e7)]
        if len(tmp) < 50:
            continue
        q = pd.qcut(tmp["score"].rank(method="first"), N_LAYERS, labels=False)
        g = tmp[q == LAYER8]
        if len(g) >= 10:
            rets.append(g["fwd"].mean() - COST)
    return rets


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2018-01-01")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    print(f"[init] 股票 {len(codes)} 只, 起始 {args.start}")

    print("[1/3] 加载因子...")
    panel = load_factors(conn, codes, args.start)
    conn.close()
    fwd = []
    for code, g in panel.groupby(level="stock_code"):
        fwd.append(g["close"].shift(-FREQ) / g["close"] - 1.0)
    panel["fwd_5"] = pd.concat(fwd).sort_index()
    panel = panel[panel["fwd_5"].notna()]
    print(f"  面板 {panel.shape}, {time.time() - t0:.0f}s")

    print("[2/3] 静态得分 + 动态得分...")
    score_static = composite_score(panel)

    # 市场状态（每调仓日，用当日之前数据判定——因子和收益同为当日截面，无未来泄漏）
    mkt = panel.groupby(level="date")["close"].mean().sort_index()
    ret60 = mkt / mkt.shift(60) - 1.0
    regime = pd.Series("震荡", index=mkt.index)
    regime[ret60 > 0.05] = "牛"
    regime[ret60 < -0.05] = "熊"
    # 只保留调仓日
    dates_all = sorted(panel.index.get_level_values("date").unique())
    rebal_dates = dates_all[::FREQ]
    regime_rebal = regime.reindex(rebal_dates).fillna("震荡")
    print(f"  市场状态分布: {regime_rebal.value_counts().to_dict()}")

    score_dynamic = dynamic_score(panel, regime_rebal)

    print("[3/3] 对比回测（层 8）...")
    ra = layer8_returns(panel, score_static)
    rb = layer8_returns(panel, score_dynamic)
    _, ma = net_value(ra, 0)
    _, mb = net_value(rb, 0)

    print(f"\n{'=' * 64}\n  层 8 对比（{args.start} ~ 今, 20日调仓）\n{'=' * 64}")
    print(f"{'方案':<22}{'年化':>8}{'累计':>9}{'Sharpe':>8}{'回撤':>9}{'期数':>6}")
    print(f"  静态反转(当前v2)  {ma['ann']:>7.1%}{ma['total']:>8.1%}{ma['sharpe']:>8.2f}{ma['mdd']:>8.1%}{ma['periods']:>6}")
    print(f"  动态切换(牛动量)  {mb['ann']:>7.1%}{mb['total']:>8.1%}{mb['sharpe']:>8.2f}{mb['mdd']:>8.1%}{mb['periods']:>6}")
    print(f"\n  总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
