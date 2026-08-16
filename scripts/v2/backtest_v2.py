#!/usr/bin/env python3
"""
GP 选股方案 v2 — 分层回测

流程：
  1. 全市场加载 K 线 → 计算 12 因子 + 规模代理
  2. 综合得分（市值中性化 + 反向 Z-score + 等权合成）
  3. 周频调仓：每 5 交易日按综合得分分 10 层，Top 层等权持有未来 5 日
  4. 输出：各层净值/年化/回撤/Sharpe/换手；Top 层 vs 全市场等权基准
  5. 分市场状态（牛/熊/震荡）超额收益

用法:
  python backtest_v2.py --limit 500 --start 2020-01-01   # 小规模
  python backtest_v2.py --start 2018-01-01               # 全量
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
from scorer_v2 import EFFECTIVE_FACTORS, composite_score, IC_WEIGHTS

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MIN_BARS = 250
t0 = 0.0  # 模块级计时（供 load_factors 引用）
FREQ = 20         # 20交易日调仓（匹配因子验证周期）
N_LAYERS = 10     # 十分位
COST = 0.001      # 单边交易成本 0.1%
TOP_LAYER_IDX = N_LAYERS - 1


def load_factors(conn, codes: list[str], start: str) -> pd.DataFrame:
    """逐股计算因子，返回 MultiIndex(date, stock) panel。"""
    parts = []
    for i, code in enumerate(codes):
        try:
            df = pd.read_sql(
                "SELECT trade_date, open, high, low, close, volume, amount FROM kline_data "
                "WHERE stock_code=? ORDER BY trade_date", conn, params=(code,))
            if len(df) < MIN_BARS:
                continue
            f = compute_factors_for_stock(df.set_index("trade_date"))
            f = f.reset_index()
            f["close"] = df["close"].values
            f["amt_60"] = df["amount"].rolling(60).mean().values
            f["stock_code"] = code
            f = f[f["trade_date"] >= start]
            if len(f) < 100:
                continue
            parts.append(f.set_index(["trade_date", "stock_code"]))
        except Exception:
            continue
        if (i + 1) % 1000 == 0:
            print(f"  [load] {i + 1}/{len(codes)}, {time.time() - t0:.0f}s", flush=True)
    p = pd.concat(parts)
    p.index = p.index.set_names(["date", "stock_code"])
    return p


def layer_returns(panel: pd.DataFrame, score: pd.Series, n_layers: int, freq: int,
                  min_price: float = 3.0, min_amt: float = 3e7, diag: dict | None = None):
    """周频分层：调仓日按得分分层，取未来5日收益。返回 {layer: 收益Series}。

    min_price/min_amt：流动性/价格过滤（剔除低价垃圾股）。
    """
    dates = sorted(panel.index.get_level_values("date").unique())
    rebalance = dates[::freq]
    layers = {i: [] for i in range(n_layers)}

    for d in rebalance:
        cross = panel.xs(d, level="date")
        tmp = pd.DataFrame({
            "score": score.xs(d, level="date"),
            "fwd": cross["fwd_5"],
            "close": cross["close"],
            "amt": cross["amt_60"],
        }).dropna()
        # 过滤：价格与流动性
        tmp = tmp[(tmp["close"] >= min_price) & (tmp["amt"] >= min_amt)]
        if len(tmp) < n_layers * 10:
            continue
        try:
            q = pd.qcut(tmp["score"].rank(method="first"), n_layers, labels=False)
        except ValueError:
            continue
        tmp["layer"] = q
        for i in range(n_layers):
            g = tmp[tmp["layer"] == i]
            if len(g) > 0:
                layers[i].append(g["fwd"].mean())
        # 诊断：Top 层与次顶层持仓特征（每 10 期抽样）
        if len(layers[TOP_LAYER_IDX]) % 10 == 0:
            for li in (TOP_LAYER_IDX, TOP_LAYER_IDX - 1):
                g = tmp[tmp["layer"] == li]
                if len(g) > 0:
                    diag[li].append({
                        "n": len(g), "close": g["close"].median(),
                        "amt": g["amt"].median(), "score": g["score"].median(),
                    })
    return layers


def net_value(returns: list[float], cost_per_rebalance: float = 0.0) -> tuple[pd.Series, dict]:
    """收益序列 → 净值 + 指标。cost 每次调仓成本。"""
    rets = np.array(returns) - cost_per_rebalance
    nv = np.cumprod(1 + rets)
    nv = pd.Series(nv, index=range(len(nv)))
    total = nv.iloc[-1] - 1 if len(nv) else 0
    ann_factor = 250 / FREQ  # 每年调仓次数（20日调仓 ≈ 12.5 期/年）
    ann = (1 + total) ** (ann_factor / max(len(rets), 1)) - 1 if len(rets) else 0
    std = np.std(rets, ddof=1) if len(rets) > 1 else 0
    sharpe = (np.mean(rets) / std * np.sqrt(ann_factor)) if std > 0 else 0
    peak = np.maximum.accumulate(nv)
    mdd = float(((nv - peak) / peak).min()) if len(nv) else 0
    win = float((rets > 0).mean()) if len(rets) else 0
    return nv, {"total": total, "ann": ann, "sharpe": sharpe, "mdd": mdd, "win": win, "periods": len(rets)}


def market_regime(panel: pd.DataFrame, freq: int = 20) -> pd.Series:
    """市场状态：全市场等权 60 日累计收益 → 牛/熊/震荡。"""
    mkt = panel.groupby(level="date")["fwd_5"].mean()
    ret60 = mkt.rolling(3).sum()  # 60 交易日 ≈ 3 个 20 日周期
    regime = pd.Series("震荡", index=mkt.index)
    regime[ret60 > 0.05] = "牛"
    regime[ret60 < -0.05] = "熊"
    return regime


def main():
    global t0
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--weights", default="equal", choices=["equal", "ic"], help="因子权重方案")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    if args.limit:
        codes = codes[:args.limit]
    print(f"[init] 股票 {len(codes)} 只, 起始 {args.start}")

    print("[1/4] 计算因子...")
    panel = load_factors(conn, codes, args.start)
    conn.close()
    print(f"  面板 {panel.shape}, 股票 {panel.index.get_level_values('stock_code').nunique()}, "
          f"{time.time() - t0:.0f}s")

    print("[2/4] 计算未来20日收益 + 综合得分...")
    # fwd_5（按股票内部滚动）
    fwd = []
    for code, g in panel.groupby(level="stock_code"):
        c = g["close"]
        fr = c.shift(-20) / c - 1.0
        fwd.append(fr)
    panel["fwd_5"] = pd.concat(fwd).sort_index()
    panel = panel[panel["fwd_5"].notna()]

    w = IC_WEIGHTS if args.weights == "ic" else None
    score = composite_score(panel, weights=w)
    print(f"  权重方案: {args.weights}")
    print(f"  得分样本 {score.notna().sum()}, {time.time() - t0:.0f}s")

    print("[3/4] 周频分层回测...")
    diag = {N_LAYERS - 1: [], N_LAYERS - 2: []}
    layers = layer_returns(panel, score, N_LAYERS, FREQ, diag=diag)

    print(f"\n{'=' * 74}\n  十分位分层回测（周频, 单边成本 {COST:.1%}）\n{'=' * 74}")
    print(f"{'层':<6}{'年化':>9}{'累计':>9}{'Sharpe':>8}{'最大回撤':>10}{'周胜率':>8}{'期数':>6}")
    layer_nv = {}
    for i in range(N_LAYERS):
        if len(layers[i]) < 10:
            continue
        nv, met = net_value(layers[i], COST)
        layer_nv[i] = nv
        tag = " ← Top 层" if i == TOP_LAYER_IDX else ""
        print(f"{i:<6}{met['ann']:>8.1%}{met['total']:>8.1%}{met['sharpe']:>8.2f}"
              f"{met['mdd']:>10.1%}{met['win']:>8.1%}{met['periods']:>6}{tag}")

    # 诊断输出：Top 层 vs 次顶层持仓特征
    if diag and diag.get(TOP_LAYER_IDX):
        print("\n  [诊断] Top层 vs 次顶层 持仓特征（中位数）:")
        for li in (TOP_LAYER_IDX, TOP_LAYER_IDX - 1):
            rows = diag[li]
            if rows:
                avg_n = np.mean([r["n"] for r in rows])
                avg_c = np.mean([r["close"] for r in rows])
                avg_a = np.mean([r["amt"] for r in rows])
                avg_s = np.mean([r["score"] for r in rows])
                print(f"    层{li}: 平均持仓 {avg_n:.0f} 只, 中位价 {avg_c:.1f}元, 日均成交额 {avg_a/1e4:.0f}万, 得分 {avg_s:.2f}")

    # 全市场等权基准
    mkt_ret = panel.groupby(level="date")["fwd_5"].mean()
    # 对齐到调仓日
    rebal_dates = sorted(panel.index.get_level_values("date").unique())[::FREQ]
    mkt_aligned = mkt_ret.reindex(rebal_dates).dropna()
    nv_mkt, met_mkt = net_value(mkt_aligned.tolist(), COST)
    print(f"\n  基准（全市场等权）: 年化 {met_mkt['ann']:>7.1%}  累计 {met_mkt['total']:>7.1%}  "
          f"Sharpe {met_mkt['sharpe']:.2f}  回撤 {met_mkt['mdd']:>6.1%}")

    if TOP_LAYER_IDX in layer_nv:
        top_nv = layer_nv[TOP_LAYER_IDX]
        # 对齐长度
        n = min(len(top_nv), len(nv_mkt))
        excess = top_nv.iloc[:n] - nv_mkt.iloc[:n]
        print(f"  Top 层超额（vs 等权基准, 累计）: {excess.iloc[-1]:>+7.1%}")

    print("\n[4/4] 分市场状态验证（Top 层 vs 等权）...")
    mkt_ret_full = panel.groupby(level="date")["fwd_5"].mean()
    regime = market_regime(panel, freq=FREQ)
    rebal = sorted(panel.index.get_level_values("date").unique())[::FREQ]
    top_rets = pd.Series(layers[TOP_LAYER_IDX], index=rebal[:len(layers[TOP_LAYER_IDX])])
    mkt_r = mkt_ret_full.reindex(rebal).dropna()
    top_r = top_rets.reindex(mkt_r.index).dropna()
    if len(top_r) > 20:
        for st in ["牛", "熊", "震荡"]:
            m = (regime.reindex(mkt_r.index) == st) & top_r.notna()
            if m.sum() >= 5:
                ex = (top_r[m] - mkt_r[m]).mean()
                print(f"  {st}市: {m.sum():>4} 期, Top 超额/期 {ex:>+7.2%}")

    print(f"\n总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
