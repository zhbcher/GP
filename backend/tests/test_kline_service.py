"""K线服务核心逻辑测试：复权计算（qfq/hfq）。"""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.kline_service import compute_adjusted


def _row(timestamp, o, h, l, c):
    return type("K", (), {
        "timestamp": timestamp, "open": o, "high": h, "low": l, "close": c,
        "volume": 1000, "turnover": 100000,
    })()


def _ts(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def test_qfq_anchor_latest():
    """qfq 以最新价为锚：最新一天复权价 = 原始价。"""
    data = [_row(_ts("2026-01-01"), 10, 11, 9, 10.5),
            _row(_ts("2026-02-01"), 12, 13, 11, 12.0)]
    # 2026-02-01 除权 factor=0.5（10 送 10）
    factors = {"2026-02-01": 0.5}
    out = compute_adjusted(data, factors, "qfq")
    assert out[-1].close == 12.0  # 最新一天锚定原始价
    # 除权前（2026-01-01）复权 = 原始 × (latest_factor / factor_for(date)) = 10.5 × (0.5/1.0)
    assert abs(out[0].close - 10.5 * 0.5) < 0.01


def test_hfq_anchor_oldest():
    """hfq 以最早价为锚：除权前价格 = 原始价。"""
    data = [_row(_ts("2026-01-01"), 10, 11, 9, 10.5),
            _row(_ts("2026-02-01"), 12, 13, 11, 12.0)]
    factors = {"2026-02-01": 0.5}
    out = compute_adjusted(data, factors, "hfq")
    assert out[0].close == 10.5  # 最早一天锚定原始价
    assert abs(out[-1].close - 12.0 / 0.5) < 0.01  # 除权后放大


def test_no_factors_returns_unchanged():
    """无除权事件时，复权 = 原始数据。"""
    data = [_row(_ts("2026-01-01"), 10, 11, 9, 10.5)]
    out = compute_adjusted(data, {}, "qfq")
    assert out[0].close == 10.5
    assert out[0].open == 10.0
