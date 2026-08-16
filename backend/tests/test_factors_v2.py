"""因子计算测试：scripts/v2/factors_v2.py（向量化因子输出）。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "v2"))

from factors_v2 import compute_factors_for_stock, KLINE_FACTORS
from scorer_v2 import EFFECTIVE_FACTORS, composite_score


def _sample_panel(n=300):
    rng = np.random.default_rng(7)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    c = 10 * np.cumprod(1 + rng.normal(0, 0.02, n))
    df = pd.DataFrame({
        "trade_date": dates.strftime("%Y-%m-%d"),
        "open": c * 0.99, "high": c * 1.02, "low": c * 0.98, "close": c,
        "volume": rng.integers(10000, 5000000, n).astype(float),
        "amount": rng.integers(10000, 5000000, n).astype(float) * c * 100,
    })
    return df.set_index("trade_date")


def test_all_kline_factors_computed():
    """12 个 K 线因子全部输出，且后段有有效值。"""
    df = _sample_panel()
    f = compute_factors_for_stock(df)
    for k in KLINE_FACTORS:
        assert k in f.columns, f"缺少因子 {k}"
        assert f[k].notna().sum() > 50, f"因子 {k} 有效值过少"


def test_factor_head_nan():
    """因子序列前段为 NaN（窗口不足），后段有效。"""
    df = _sample_panel()
    f = compute_factors_for_stock(df)
    assert np.isnan(f["M1_rps20"].iloc[:19]).all()  # 20 日窗口前 19 天为 NaN
    assert np.isfinite(f["M1_rps20"].iloc[-1])


def test_composite_score_cross_section_mean_zero():
    """综合得分每日期截面均值为 0。"""
    rng = np.random.default_rng(0)
    n_stocks, n_dates = 50, 20
    dates = pd.date_range("2024-01-01", periods=n_dates, freq="B")
    idx = pd.MultiIndex.from_product(
        [dates.strftime("%Y-%m-%d"), [f"s{i}" for i in range(n_stocks)]],
        names=["date", "stock_code"])
    p = pd.DataFrame(index=idx)
    p["amt_60"] = rng.uniform(1e7, 1e10, len(p))
    for k in EFFECTIVE_FACTORS:
        p[k] = rng.normal(0, 1, len(p))
    sc = composite_score(p)
    means = sc.groupby(level="date").mean()
    assert np.allclose(means.abs(), 0, atol=1e-6)
