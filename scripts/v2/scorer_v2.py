#!/usr/bin/env python3
"""
GP 选股方案 v2 — 因子合成（综合得分）

输入：因子 panel（date × stock × factor）
流程：
  1. 市值中性化（对 log60日均成交额 回归取残差）——消除规模代理
  2. 横截面 Z-score 标准化
  3. 按实证方向取反（A股20日反转/低波效应：低值加分）
  4. 加权合成综合得分（默认等权；支持 IC 加权）

用法（作为模块）:
  from scorer_v2 import composite_score, compute_cross_sectional_zscores
"""
import numpy as np
import pandas as pd

# 有效因子及方向（来自 ic_report.md 实证结果，负方向=低值加分）
EFFECTIVE_FACTORS = {
    "V2_amp":        {"name": "振幅",     "direction": -1},
    "M1_rps20":      {"name": "RPS强度",  "direction": -1},
    "M3_ma_align":   {"name": "均线排列", "direction": -1},
    "S5_vol_turn":   {"name": "换手异动", "direction": -1},
}

# ICIR（市值中性化后 20 日，来自 ic_validation 全量结果）→ IC 加权权重
# 权重 = |ICIR| / Σ|ICIR|
_ICIR = {"V2_amp": 0.435, "M1_rps20": 0.516, "M3_ma_align": 0.473, "S5_vol_turn": 0.596}
_ICIR_SUM = sum(_ICIR.values())
IC_WEIGHTS = {k: v / _ICIR_SUM for k, v in _ICIR.items()}


def neutralize(factor_panel: pd.DataFrame, fac: str) -> pd.Series:
    """市值中性化：对 log(60日均成交额+1) 回归取残差。"""
    dates = factor_panel.index.get_level_values("date")
    amt = factor_panel["amt_60"]
    vals = factor_panel[fac]
    x = np.log(amt + 1.0).to_numpy(dtype=float)
    y = vals.to_numpy(dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    resid = pd.Series(np.nan, index=factor_panel.index)
    if mask.sum() < 30:
        return resid
    beta = np.polyfit(x[mask], y[mask], 1)
    resid.loc[mask] = y[mask] - (beta[0] * x[mask] + beta[1])
    return resid


def winsorize(s: pd.Series, lo: float = 0.02, hi: float = 0.98) -> pd.Series:
    """按分位数缩尾，抑制极值端失效。"""
    q_lo, q_hi = s.quantile(lo), s.quantile(hi)
    return s.clip(q_lo, q_hi)


def compute_cross_sectional_zscores(
    factor_panel: pd.DataFrame,
    factor_cols: list[str] | None = None,
    neutralize_flag: bool = True,
    winsorize_flag: bool = True,
) -> pd.DataFrame:
    """对每个交易日横截面做 Z-score。返回同索引 DataFrame（列为因子）。"""
    cols = factor_cols or list(EFFECTIVE_FACTORS.keys())
    out = pd.DataFrame(index=factor_panel.index)
    for fac in cols:
        if neutralize_flag:
            s = neutralize(factor_panel, fac)
        else:
            s = factor_panel[fac]
        if winsorize_flag:
            s = s.groupby(level="date").transform(lambda x: winsorize(x))
        out[fac] = s.groupby(level="date").transform(
            lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0.0)
    return out


def dynamic_score(
    factor_panel: pd.DataFrame,
    regime_by_date: pd.Series,
    neutralize_flag: bool = True,
) -> pd.Series:
    """市场状态动态得分：牛/熊/震荡 切换因子方向。

    实证依据（stage3）：反转/低波因子在熊市/震荡市超额显著（+4.5~+10.9点/年），
    牛市超额平淡甚至为负（牛市弱势股跑输）。因此：
      - 牛 市: 动量方向（M1/M3 正向追强）+ 低振幅
      - 熊/震荡: 反转方向（M1/M3 反向超跌）+ 低振幅 + 缩量

    regime_by_date: index=date, value=牛/熊/震荡。
    返回综合得分 Series（index 同 factor_panel）。
    """
    cols = list(EFFECTIVE_FACTORS.keys())
    zs = compute_cross_sectional_zscores(factor_panel, cols, neutralize_flag)
    score = pd.Series(0.0, index=factor_panel.index)
    dates = factor_panel.index.get_level_values("date")
    for fac in cols:
        z = zs[fac]
        # 逐期根据 regime 决定方向
        for d in z.index.get_level_values("date").unique():
            reg = regime_by_date.get(d, "震荡")
            if reg == "牛" and fac in ("M1_rps20", "M3_ma_align"):
                direction = 1.0   # 牛市动量正向
            elif fac == "V2_amp":
                direction = -1.0  # 低振幅始终正向
            else:
                direction = EFFECTIVE_FACTORS[fac]["direction"]  # 反转/缩量
            score.loc[d] += direction * z.loc[d].fillna(0.0)
    # 等权归一化
    score = score / len(cols)
    return score


def composite_score(
    factor_panel: pd.DataFrame,
    weights: dict[str, float] | None = None,
    neutralize_flag: bool = True,
    winsorize_flag: bool = True,
    factor_cols: list[str] | None = None,
) -> pd.Series:
    """综合得分 = Σ direction_i × weight_i × zscore_i。

    weights: 因子权重（默认等权）；direction 已在 EFFECTIVE_FACTORS 定义。
    返回 Series（index 同 factor_panel，值为综合得分）。
    """
    cols = factor_cols or list(EFFECTIVE_FACTORS.keys())
    if weights is None:
        w = {c: 1.0 / len(cols) for c in cols}
    else:
        w = weights
    zs = compute_cross_sectional_zscores(factor_panel, cols, neutralize_flag, winsorize_flag)
    score = pd.Series(0.0, index=factor_panel.index)
    for fac in cols:
        d = EFFECTIVE_FACTORS[fac]["direction"]
        score += d * w.get(fac, 0) * zs[fac]
    return score


if __name__ == "__main__":
    # 自测
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    idx = pd.MultiIndex.from_product([dates.strftime("%Y-%m-%d"), [f"s{i}" for i in range(50)]],
                                     names=["date", "stock_code"])
    p = pd.DataFrame(index=idx)
    p["amt_60"] = rng.uniform(1e7, 1e10, len(p))
    p["V2_amp"] = rng.normal(0.04, 0.01, len(p))
    p["M1_rps20"] = rng.normal(0, 0.2, len(p))
    p["M3_ma_align"] = rng.integers(0, 4, len(p))
    p["S5_vol_turn"] = rng.uniform(0.5, 2.5, len(p))
    sc = composite_score(p)
    print("综合得分: 样本数", sc.notna().sum(), "范围", round(sc.min(), 3), "~", round(sc.max(), 3))
    print("每日期截面得分均值应≈0:", sc.groupby(level="date").mean().round(6).unique())
