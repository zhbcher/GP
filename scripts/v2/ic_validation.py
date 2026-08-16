#!/usr/bin/env python3
"""
GP 选股方案 v2 — 单因子 IC 回测验证

对 K 线可计算的 12 个因子做横截面有效性检验：
  - 周频（每 5 交易日）截面 Spearman IC（因子 vs 未来 5 日 / 20 日收益）
  - 汇总：IC 均值、ICIR、IC>0 胜率、|IC| 均值
  - 五分位分层：Top 层 - Bottom 层未来收益差（单调性 / 多空收益）

用法:
  python ic_validation.py --limit 300 --start 2023-01-01   # 小规模验证
  python ic_validation.py --start 2018-01-01               # 全量
  python ic_validation.py --horizon 20                     # 用 20 日收益
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from factors_v2 import KLINE_FACTORS, compute_factors_for_stock

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MIN_BARS = 250  # 至少 1 年数据才纳入


def load_market_ret(conn) -> pd.Series:
    """市场日收益（全市场等权平均，用于特质波动率回归）。"""
    df = pd.read_sql("SELECT trade_date, close FROM kline_data WHERE stock_code='sh000001' ORDER BY trade_date", conn)
    # sh000001 是上证指数? 实际用全市场均值更稳，这里用抽样等权
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data LIMIT 200", conn)["stock_code"].tolist()
    rets = []
    for code in codes[:50]:
        d = pd.read_sql(
            "SELECT trade_date, close FROM kline_data WHERE stock_code=? ORDER BY trade_date", conn, params=(code,))
        if len(d) > 100:
            r = d.set_index("trade_date")["close"].pct_change()
            rets.append(r)
    if rets:
        mkt = pd.concat(rets, axis=1).mean(axis=1)
        return mkt
    return None


def compute_stock_factors(conn, code: str, mkt_ret: pd.Series | None) -> pd.DataFrame | None:
    """计算单只股票的因子 panel。返回 DataFrame[date, factor...] 或 None。"""
    df = pd.read_sql(
        "SELECT trade_date, open, high, low, close, volume, amount FROM kline_data "
        "WHERE stock_code=? ORDER BY trade_date", conn, params=(code,))
    if len(df) < MIN_BARS:
        return None
    f = compute_factors_for_stock(df.set_index("trade_date"), mkt_ret)
    out = f.reset_index()
    out["close"] = df["close"].values  # 保留 close 供未来收益计算
    out["amt_60"] = df["amount"].rolling(60).mean().values  # 规模代理（60日均成交额）
    return out


def compute_forward_returns(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """计算未来 horizon 日收益（在股票内部）。"""
    closes = df["close"].to_numpy(dtype=float)
    fwd = np.full(len(closes), np.nan)
    fwd[:len(closes) - horizon] = closes[horizon:] / closes[:len(closes) - horizon] - 1.0
    df[f"fwd_{horizon}"] = fwd
    return df


def run_ic_analysis(factor_panel: pd.DataFrame, horizon: int, freq: int = 5, neutralize: bool = False):
    """对 factor_panel (MultiIndex: date, stock) 做周频横截面 IC 分析。

    neutralize=True 时，因子先对 log(规模代理=60日均成交额) 回归取残差（市值中性化）。
    """
    results = {}
    dates = sorted(factor_panel.index.get_level_values("date").unique())
    sample_dates = dates[::freq]  # 每 freq 交易日取样

    for fac in KLINE_FACTORS:
        ics = []
        for d in sample_dates:
            cross = factor_panel.xs(d, level="date")[[fac, f"fwd_{horizon}"]].dropna()
            if len(cross) < 30:
                continue
            if neutralize:
                # 市值中性化：对 log(60日均成交额) 回归取残差
                amt60 = factor_panel.xs(d, level="date")[["amt_60"]]
                tmp = cross.join(amt60).dropna()
                if len(tmp) < 30 or tmp["amt_60"].std() == 0:
                    continue
                import numpy as _np
                x = _np.log(tmp["amt_60"] + 1).to_numpy()
                y = tmp[fac].to_numpy()
                mask = _np.isfinite(x) & _np.isfinite(y)
                if mask.sum() < 30:
                    continue
                beta = _np.polyfit(x[mask], y[mask], 1)
                resid = pd.Series(y - (beta[0] * x + beta[1]), index=tmp.index)
                ic = resid.rank().corr(tmp[f"fwd_{horizon}"].rank())
            else:
                ic = cross[fac].rank().corr(cross[f"fwd_{horizon}"].rank())
            if np.isfinite(ic):
                ics.append(ic)
        ics = np.array(ics)
        if len(ics) < 10:
            results[fac] = {"samples": len(ics)}
            continue
        results[fac] = {
            "samples": len(ics),
            "ic_mean": round(float(ics.mean()), 4),
            "icir": round(float(ics.mean() / ics.std()), 3) if ics.std() > 0 else 0.0,
            "ic_positive_pct": round(float((ics > 0).mean()), 3),
            "abs_ic_mean": round(float(np.abs(ics).mean()), 4),
        }
    return results


def run_layered_analysis(factor_panel: pd.DataFrame, horizon: int, freq: int = 5, n_layers: int = 5):
    """五分位分层：Top 层 vs Bottom 层未来收益。"""
    results = {}
    dates = sorted(factor_panel.index.get_level_values("date").unique())
    sample_dates = dates[::freq]

    for fac in KLINE_FACTORS:
        top_rets, bot_rets = [], []
        for d in sample_dates:
            cross = factor_panel.xs(d, level="date")[[fac, f"fwd_{horizon}"]].dropna()
            if len(cross) < n_layers * 10:
                continue
            try:
                q = pd.qcut(cross[fac].rank(method="first"), n_layers, labels=False)
            except ValueError:
                continue
            cross["layer"] = q
            top = cross[cross["layer"] == n_layers - 1][f"fwd_{horizon}"]
            bot = cross[cross["layer"] == 0][f"fwd_{horizon}"]
            if len(top) >= 5 and len(bot) >= 5:
                top_rets.append(top.mean())
                bot_rets.append(bot.mean())
        if len(top_rets) >= 10:
            results[fac] = {
                "top_mean": round(float(np.mean(top_rets)) * 100, 2),
                "bot_mean": round(float(np.mean(bot_rets)) * 100, 2),
                "spread": round((np.mean(top_rets) - np.mean(bot_rets)) * 100, 2),
                "periods": len(top_rets),
            }
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="限制股票数量（0=全部）")
    ap.add_argument("--start", default="2018-01-01", help="起始日期")
    ap.add_argument("--horizon", type=int, default=5, help="预测期（交易日）")
    ap.add_argument("--neutralize", action="store_true", help="市值中性化（对60日均成交额回归取残差）")
    args = ap.parse_args()

    t0 = time.time()
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    if args.limit:
        codes = codes[:args.limit]
    print(f"[init] 股票 {len(codes)} 只, 起始 {args.start}, 预测期 {args.horizon} 日, 中性化={args.neutralize}")

    print("[init] 计算市场收益基准...")
    mkt_ret = None  # 简化：特质波动率用自身收益近似（避免额外 IO）

    print("[init] 逐股计算因子...")
    panels = []
    for i, code in enumerate(codes):
        try:
            df = compute_stock_factors(conn, code, mkt_ret)
            if df is None:
                continue
            df = compute_forward_returns(df, args.horizon)
            df = df[df["trade_date"] >= args.start]
            if len(df) < 100:
                continue
            df["stock_code"] = code
            df = df.set_index(["trade_date", "stock_code"])
            panels.append(df)
        except Exception as e:
            if i % 200 == 0:
                print(f"  [{i}] {code} 跳过: {type(e).__name__} {str(e)[:60]}")
            continue
        if (i + 1) % 500 == 0:
            print(f"  [{i + 1}/{len(codes)}] 已计算 {len(panels)} 只, {time.time() - t0:.0f}s")
    conn.close()

    if not panels:
        print("[fatal] 无有效数据")
        sys.exit(1)

    panel = pd.concat(panels)
    panel.index = panel.index.set_names(["date", "stock_code"])
    print(f"[done] 面板: {panel.shape}, 股票 {panel.index.get_level_values('stock_code').nunique()} 只, "
          f"日期 {panel.index.get_level_values('date').min()} ~ {panel.index.get_level_values('date').max()}, "
          f"耗时 {time.time() - t0:.0f}s")

    # IC 分析
    print(f"\n{'=' * 78}\n  IC 分析（预测期 {args.horizon} 日, 周频截面）\n{'=' * 78}")
    print(f"{'因子':<18}{'样本':>6}{'IC均值':>9}{'ICIR':>8}{'IC>0占比':>10}{'|IC|均值':>10}")
    ic_res = run_ic_analysis(panel, args.horizon, neutralize=args.neutralize)
    for fac in KLINE_FACTORS:
        r = ic_res.get(fac, {})
        if "ic_mean" not in r:
            print(f"{fac:<18}{r.get('samples', 0):>6}   (样本不足)")
            continue
        print(f"{fac:<18}{r['samples']:>6}{r['ic_mean']:>9}{r['icir']:>8}{r['ic_positive_pct']:>10}{r['abs_ic_mean']:>10}")

    # 分层分析
    print(f"\n{'=' * 78}\n  五分位分层（Top 层 vs Bottom 层, {args.horizon} 日收益 %）\n{'=' * 78}")
    print(f"{'因子':<18}{'Top层':>9}{'Bottom层':>11}{'多空差':>9}{'期数':>6}")
    layer_res = run_layered_analysis(panel, args.horizon)
    for fac in KLINE_FACTORS:
        r = layer_res.get(fac, {})
        if "spread" not in r:
            continue
        print(f"{fac:<18}{r['top_mean']:>9}{r['bot_mean']:>11}{r['spread']:>9}{r['periods']:>6}")

    # 汇总筛选建议（方向由实证 IC 符号决定，不强制预设方向）
    print(f"\n{'=' * 78}\n  因子初筛建议（|IC|≥0.02 且 |多空差|≥0.5% 视为有效；IC>0=高值→高收益）\n{'=' * 78}")
    for fac in KLINE_FACTORS:
        r = ic_res.get(fac, {})
        lr = layer_res.get(fac, {})
        ic = r.get("ic_mean", 0)
        spread = lr.get("spread", 0)
        if abs(ic) >= 0.02 and abs(spread) >= 0.5:
            verdict = f"✅ 有效（方向: {'正向' if ic > 0 else '反向'}）"
        elif abs(ic) >= 0.01:
            verdict = "⚠️ 弱/待观察"
        else:
            verdict = "❌ 无效"
        print(f"  {fac:<18} IC={ic:>8} 多空差={spread:>7}%  → {verdict}")
    print(f"\n总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
