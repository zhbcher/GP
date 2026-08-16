#!/usr/bin/env python3
"""
GP 选股方案 v2 — 因子计算库（20 因子）【向量化版本】

与现有超跌反弹因子（scripts/factors.py）完全隔离。
输入：单只股票 OHLCV 序列（pandas DataFrame，trade_date 升序）
输出：同索引 DataFrame，列为因子名。

性能：全部用 pandas rolling 向量化，避免 Python 逐日循环。

因子清单（K线可算 12 个，外部数据 8 个占位）：
  动量/趋势:  M1 RPS强度  M2 12-1月动量  M3 均线多头排列  M4 均线收敛发散
  量价结构:   S1 聪明钱(近似)  S2 量价相关  S3 上下影线  S4 筹码集中度  S5 换手异动
  波动率:     V1 特质波动率  V2 振幅  V3 波动率压缩
  资金面:     F1-F3   需外部数据源
  价值质量:   Q1-Q5   需财务数据
"""
import numpy as np
import pandas as pd

FACTOR_META = {
    "M1_rps20":      {"dim": "momentum", "name": "RPS强度20日", "direction": "pos"},
    "M2_mom_12_1":   {"dim": "momentum", "name": "12-1月动量", "direction": "pos"},
    "M3_ma_align":   {"dim": "momentum", "name": "均线多头排列", "direction": "pos"},
    "M4_ma_conv":    {"dim": "momentum", "name": "均线收敛发散", "direction": "pos"},
    "S1_smart_money": {"dim": "price_vol", "name": "聪明钱近似", "direction": "pos"},
    "S2_pv_corr":     {"dim": "price_vol", "name": "量价相关", "direction": "neg"},
    "S3_lower_shadow": {"dim": "price_vol", "name": "下影线优势", "direction": "pos"},
    "S4_chip_conc":   {"dim": "price_vol", "name": "筹码集中度", "direction": "pos"},
    "S5_vol_turn":    {"dim": "price_vol", "name": "换手异动", "direction": "pos"},
    "V1_ivol":        {"dim": "volatility", "name": "特质波动率", "direction": "neg"},
    "V2_amp":         {"dim": "volatility", "name": "振幅", "direction": "neg"},
    "V3_vol_compress": {"dim": "volatility", "name": "波动率压缩", "direction": "pos"},
    "F1_main_inflow": {"dim": "capital", "name": "主力净流入", "direction": "pos", "external": True},
    "F2_north_chg":   {"dim": "capital", "name": "北向变化", "direction": "pos", "external": True},
    "F3_block_disc":  {"dim": "capital", "name": "大宗折溢价", "direction": "pos", "external": True},
    "Q1_ffscore":     {"dim": "value", "name": "FFScore", "direction": "pos", "external": True},
    "Q2_value":       {"dim": "value", "name": "低估值", "direction": "pos", "external": True},
    "Q3_dividend":    {"dim": "value", "name": "高股息", "direction": "pos", "external": True},
    "Q4_growth":      {"dim": "value", "name": "盈利增长", "direction": "pos", "external": True},
    "Q5_roe_stab":    {"dim": "value", "name": "ROE稳定", "direction": "pos", "external": True},
}
KLINE_FACTORS = [k for k, v in FACTOR_META.items() if not v.get("external")]


def compute_factors_for_stock(
    df: pd.DataFrame,
    mkt_ret: pd.Series | None = None,
) -> pd.DataFrame:
    """计算单只股票全部 K 线因子。df 需含 trade_date/open/high/low/close/volume/amount。

    mkt_ret: 市场日收益 Series（index=trade_date），用于特质波动率；缺省用自身收益近似。
    返回 DataFrame（index=trade_date），因子列名见 KLINE_FACTORS。
    """
    o = df["open"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    a = df["amount"].astype(float)
    idx = df.index

    ret = c.pct_change()
    out = pd.DataFrame(index=idx)

    # ── M1 RPS 强度：20 日收益（截面排名在 IC 阶段）──────────────────────────
    out["M1_rps20"] = c.pct_change(20)

    # ── M2 12-1 月动量：60日动量 − 20日动量（剔除近月反转）──────────────────
    out["M2_mom_12_1"] = c.pct_change(60) - c.pct_change(20)

    # ── M3 均线多头排列：MA5>MA10>MA20>MA60 计分 0~3 ────────────────────────
    ma5, ma10, ma20, ma60 = (c.rolling(n).mean() for n in (5, 10, 20, 60))
    m3 = pd.DataFrame({
        "a": (ma5 > ma10).astype(float),
        "b": (ma10 > ma20).astype(float),
        "c": (ma20 > ma60).astype(float),
    }).sum(axis=1)
    out["M3_ma_align"] = m3.where(m3.notna() & (ma60.notna()), 0.0)

    # ── M4 均线收敛发散：60日带宽处于低分位且收盘站上MA5 ────────────────────
    # 用 rolling 带宽序列的百分位近似（当前带宽 vs 近60日带宽分布）
    w60 = c.rolling(60)
    band60 = (w60.max() - w60.min()) / w60.min()
    w20 = c.rolling(20)
    band20 = (w20.max() - w20.min()) / w20.min()
    # 当前带宽在近60日的分位（简化：用 band20 相对 band60 历史的分位）
    band_hist = band20.rolling(60).apply(lambda x: (x <= x[-1]).mean(), raw=True)
    m4 = ((band_hist < 0.25) & (c > ma5)).astype(float)
    out["M4_ma_conv"] = m4.where(band_hist.notna(), 0.0)

    # ── S1 聪明钱近似：收盘价相对 VWAP 的偏离（20日均值）────────────────────
    vol_shares = v * 100.0
    vwap = a / vol_shares.replace(0, np.nan)
    out["S1_smart_money"] = (c / vwap - 1.0).rolling(20).mean()

    # ── S2 量价相关：20日 corr(收益, 成交量)（负相关为佳）────────────────────
    out["S2_pv_corr"] = ret.rolling(20).corr(v)

    # ── S3 下影线优势：(min(O,C)-L)/(H-L) − (H-max(O,C))/(H-L)，20日均值 ────
    rng = (h - l).replace(0, np.nan)
    lower = (np.minimum(o, c) - l) / rng
    upper = (h - np.maximum(o, c)) / rng
    out["S3_lower_shadow"] = (lower - upper).rolling(20).mean()

    # ── S4 筹码集中度：60日价格带宽（90分位−10分位）/中位价（窄=集中）────────
    hi60 = h.rolling(60).quantile(0.9)
    lo60 = l.rolling(60).quantile(0.1)
    mid60 = c.rolling(60).median()
    out["S4_chip_conc"] = ((hi60 - lo60) / mid60).where(mid60 > 0)  # 负向：越小越集中

    # ── S5 换手异动：5日均量 / 60日中位量（>1 放量，3 封顶）────────────────
    ratio = v.rolling(5).mean() / v.rolling(60).median()
    out["S5_vol_turn"] = ratio.clip(upper=3.0)

    # ── V1 特质波动率：对市场回归残差波动（20日，向量化）────────────────────
    if mkt_ret is not None:
        mkt = mkt_ret.reindex(idx)
    else:
        mkt = ret  # 简化：自身收益近似
    mkt_std = mkt.rolling(20).std()
    cov = ret.rolling(20).cov(mkt)
    beta = (cov / mkt_std ** 2).where(mkt_std > 0, 0.0)
    # 残差方差 = Var(ret) − β²·Var(mkt)
    resid_var = (ret.rolling(20).var() - beta ** 2 * mkt.rolling(20).var()).clip(lower=0)
    out["V1_ivol"] = np.sqrt(resid_var)

    # ── V2 振幅：20日均振幅（负向：低振幅为佳）──────────────────────────────
    amp = ((h - l) / c.replace(0, np.nan)).rolling(20).mean()
    out["V2_amp"] = amp

    # ── V3 波动率压缩：当前20日带宽在近60日带宽分布中的分位（低=压缩）──────
    out["V3_vol_compress"] = band_hist  # 复用 M4 的分位序列（0~1，低=压缩）

    return out


def compute_factors_batch(
    df: pd.DataFrame,
    mkt_ret: pd.Series | None = None,
) -> pd.DataFrame:
    """批量计算（多股票）：df 需含 stock_code + OHLCV 列，按 stock_code 分组。"""
    parts = []
    for code, g in df.groupby("stock_code"):
        g = g.sort_values("trade_date").set_index("trade_date")
        try:
            f = compute_factors_for_stock(g, mkt_ret)
            f["stock_code"] = code
            parts.append(f.reset_index())
        except Exception:
            continue
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


if __name__ == "__main__":
    # 自测
    rng = np.random.default_rng(42)
    n = 500
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    c = 10 * np.cumprod(1 + rng.normal(0, 0.02, n))
    df = pd.DataFrame({
        "trade_date": dates.strftime("%Y-%m-%d"),
        "open": c * 0.99, "high": c * 1.02, "low": c * 0.98, "close": c,
        "volume": rng.integers(10000, 5000000, n).astype(float),
        "amount": rng.integers(10000, 5000000, n).astype(float) * c * 100,
    })
    f = compute_factors_for_stock(df.set_index("trade_date"))
    print("K线因子:", KLINE_FACTORS)
    for k in KLINE_FACTORS:
        arr = f[k]
        print(f"  {k:<18} 有效={arr.notna().sum():>3} 最新={arr.iloc[-1] if pd.notna(arr.iloc[-1]) else 'NaN'}")
