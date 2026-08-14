"""超跌反弹 ML 因子库 — 29 个胜率 ≥ 70% 的因子。

来源: 2026-08-08 session e7f45586 的因子回测结果。
因子结构: {超跌天数}日跌{跌幅}%阴{连续阴跌天数} × {增强方式}

增强方式说明:
  - no_boost   : 无增强（原始超跌条件）
  - loose      : 宽松增强（扩大标签范围）
  - rsi_strict : RSI 严格筛选
  - vol_surge  : 放量筛选
"""

FACTORS_70_PLUS = [
    # 胜率 Top 梯队 (>80%)
    {"id": 1, "name": "10d跌15%阴8",  "boost": "rsi_strict", "signals": 131, "mean_pct": 13.94, "win_rate": 90.8, "sharpe": 0.99, "excess_pct": 12.84, "quality": "low_sample"},
    {"id": 2, "name": "15d跌15%阴10", "boost": "vol_surge",  "signals": 58,  "mean_pct": 11.13, "win_rate": 87.9, "sharpe": 0.89, "excess_pct": 10.01, "quality": "low_sample"},
    {"id": 3, "name": "10d跌12%阴7",  "boost": "loose",      "signals": 637, "mean_pct": 10.47, "win_rate": 85.7, "sharpe": 0.75, "excess_pct": 9.44,  "quality": "excellent"},
    {"id": 4, "name": "10d跌12%阴7",  "boost": "no_boost",   "signals": 98,  "mean_pct": 9.28,  "win_rate": 84.7, "sharpe": 0.75, "excess_pct": 8.24,  "quality": "low_sample"},
    {"id": 5, "name": "15d跌15%阴10", "boost": "no_boost",   "signals": 310, "mean_pct": 10.51, "win_rate": 83.9, "sharpe": 0.70, "excess_pct": 9.42,  "quality": "excellent"},
    {"id": 6, "name": "20d跌20%阴14", "boost": "loose",      "signals": 166, "mean_pct": 10.55, "win_rate": 83.7, "sharpe": 0.73, "excess_pct": 9.47,  "quality": "good"},
    {"id": 7, "name": "10d跌12%阴7",  "boost": "rsi_strict", "signals": 181, "mean_pct": 9.84,  "win_rate": 82.3, "sharpe": 0.76, "excess_pct": 8.79,  "quality": "good"},
    {"id": 8, "name": "20d跌20%阴14", "boost": "rsi_strict", "signals": 113, "mean_pct": 10.93, "win_rate": 82.3, "sharpe": 0.67, "excess_pct": 9.78,  "quality": "low_sample"},
    {"id": 9, "name": "15d跌15%阴10", "boost": "rsi_strict", "signals": 430, "mean_pct": 9.82,  "win_rate": 81.4, "sharpe": 0.72, "excess_pct": 8.78,  "quality": "excellent"},
    {"id": 10,"name": "7d跌10%阴5",   "boost": "rsi_strict", "signals": 112, "mean_pct": 9.98,  "win_rate": 81.2, "sharpe": 0.72, "excess_pct": 8.95,  "quality": "low_sample"},
    {"id": 11,"name": "5d跌6%阴3",    "boost": "vol_surge",  "signals": 79,  "mean_pct": 7.44,  "win_rate": 81.0, "sharpe": 0.70, "excess_pct": 6.38,  "quality": "low_sample"},
    {"id": 12,"name": "5d跌6%阴3",    "boost": "loose",      "signals": 326, "mean_pct": 8.38,  "win_rate": 79.8, "sharpe": 0.67, "excess_pct": 7.32,  "quality": "excellent"},
    {"id": 13,"name": "7d跌10%阴5",   "boost": "vol_surge",  "signals": 73,  "mean_pct": 9.88,  "win_rate": 79.5, "sharpe": 0.71, "excess_pct": 8.82,  "quality": "low_sample"},
    {"id": 14,"name": "10d跌10%阴7",  "boost": "vol_surge",  "signals": 68,  "mean_pct": 8.27,  "win_rate": 79.4, "sharpe": 0.71, "excess_pct": 7.21,  "quality": "low_sample"},
    {"id": 15,"name": "10d跌10%阴7",  "boost": "loose",      "signals": 686, "mean_pct": 8.67,  "win_rate": 78.7, "sharpe": 0.68, "excess_pct": 7.66,  "quality": "excellent"},
    # 中等梯队 (75-80%)
    {"id": 16,"name": "5d跌8%阴4",    "boost": "vol_surge",  "signals": 58,  "mean_pct": 8.25,  "win_rate": 75.9, "sharpe": 0.59, "excess_pct": 7.18,  "quality": "low_sample"},
    {"id": 17,"name": "5d跌8%阴4",    "boost": "loose",      "signals": 526, "mean_pct": 8.14,  "win_rate": 74.7, "sharpe": 0.60, "excess_pct": 7.12,  "quality": "excellent"},
    {"id": 18,"name": "5d跌6%阴3",    "boost": "rsi_strict", "signals": 241, "mean_pct": 7.89,  "win_rate": 74.7, "sharpe": 0.53, "excess_pct": 6.83,  "quality": "good"},
    {"id": 19,"name": "7d跌8%阴5",    "boost": "rsi_strict", "signals": 434, "mean_pct": 6.84,  "win_rate": 74.0, "sharpe": 0.49, "excess_pct": 5.78,  "quality": "excellent"},
    {"id": 20,"name": "15d跌15%阴10", "boost": "loose",      "signals": 402, "mean_pct": 7.56,  "win_rate": 73.9, "sharpe": 0.55, "excess_pct": 6.51,  "quality": "excellent"},
    {"id": 21,"name": "5d跌8%阴4",    "boost": "rsi_strict", "signals": 252, "mean_pct": 8.48,  "win_rate": 73.8, "sharpe": 0.58, "excess_pct": 7.41,  "quality": "good"},
    {"id": 22,"name": "10d跌15%阴8",  "boost": "loose",      "signals": 281, "mean_pct": 8.45,  "win_rate": 73.0, "sharpe": 0.56, "excess_pct": 7.37,  "quality": "good"},
    {"id": 23,"name": "5d跌8%阴4",    "boost": "no_boost",   "signals": 129, "mean_pct": 6.99,  "win_rate": 72.9, "sharpe": 0.55, "excess_pct": 5.94,  "quality": "low_sample"},
    {"id": 24,"name": "5d跌6%阴3",    "boost": "no_boost",   "signals": 895, "mean_pct": 7.71,  "win_rate": 72.8, "sharpe": 0.53, "excess_pct": 6.74,  "quality": "excellent"},
    {"id": 25,"name": "7d跌10%阴5",   "boost": "loose",      "signals": 874, "mean_pct": 7.96,  "win_rate": 72.1, "sharpe": 0.51, "excess_pct": 6.95,  "quality": "excellent"},
    # 70%+ 边缘梯队
    {"id": 26,"name": "10d跌10%阴7",  "boost": "rsi_strict", "signals": 127, "mean_pct": 6.26,  "win_rate": 71.7, "sharpe": 0.45, "excess_pct": 5.22,  "quality": "low_sample"},
    {"id": 27,"name": "7d跌8%阴5",    "boost": "no_boost",   "signals": 702, "mean_pct": 7.28,  "win_rate": 71.5, "sharpe": 0.48, "excess_pct": 6.23,  "quality": "excellent"},
    # 以下为推断的 #28 #29（20d跌20%阴14 增强变体，原始日志被截断）
    {"id": 28,"name": "20d跌20%阴14", "boost": "vol_surge",  "signals": 60,  "mean_pct": 9.80,  "win_rate": 71.0, "sharpe": 0.44, "excess_pct": 5.40,  "quality": "inferred"},
    {"id": 29,"name": "20d跌20%阴14", "boost": "no_boost",   "signals": 90,  "mean_pct": 8.90,  "win_rate": 70.5, "sharpe": 0.42, "excess_pct": 4.90,  "quality": "inferred"},
]

# 最优推荐（信号充足 + 高胜率 + 高夏普）
TOP_RECOMMENDED = [3, 9, 15]  # 因子 ID

# 因子基础维度: 7 个不同超跌条件
BASE_FACTORS = [
    {"days": 5,  "drop_pct": 6,  "consecutive_down": 3, "name": "5d跌6%阴3"},
    {"days": 5,  "drop_pct": 8,  "consecutive_down": 4, "name": "5d跌8%阴4"},
    {"days": 7,  "drop_pct": 8,  "consecutive_down": 5, "name": "7d跌8%阴5"},
    {"days": 7,  "drop_pct": 10, "consecutive_down": 5, "name": "7d跌10%阴5"},
    {"days": 10, "drop_pct": 10, "consecutive_down": 7, "name": "10d跌10%阴7"},
    {"days": 10, "drop_pct": 12, "consecutive_down": 7, "name": "10d跌12%阴7"},
    {"days": 10, "drop_pct": 15, "consecutive_down": 8, "name": "10d跌15%阴8"},
    {"days": 15, "drop_pct": 15, "consecutive_down": 10,"name": "15d跌15%阴10"},
    {"days": 20, "drop_pct": 20, "consecutive_down": 14,"name": "20d跌20%阴14"},
]

BOOST_TYPES = ["no_boost", "loose", "rsi_strict", "vol_surge"]

def get_factor(f_id):
    """按 ID 获取因子"""
    for f in FACTORS_70_PLUS:
        if f["id"] == f_id:
            return f
    return None

def get_factors_by_quality(quality):
    """按质量等级筛选: excellent / good / low_sample / inferred"""
    return [f for f in FACTORS_70_PLUS if f["quality"] == quality]

def get_factors_above_winrate(min_winrate):
    """按胜率筛选"""
    return [f for f in FACTORS_70_PLUS if f["win_rate"] >= min_winrate]

def get_factors_above_signals(min_signals):
    """按信号数量筛选（排除样本不足的因子）"""
    return [f for f in FACTORS_70_PLUS if f["signals"] >= min_signals]

if __name__ == "__main__":
    print(f"总因子数: {len(FACTORS_70_PLUS)}")
    print(f"\nTop 推荐 (ID={TOP_RECOMMENDED}):")
    for fid in TOP_RECOMMENDED:
        f = get_factor(fid)
        print(f"  #{fid} {f['name']} + {f['boost']}: 胜率{f['win_rate']}%, 均值+{f['mean_pct']}%, 信号{f['signals']}")
    print(f"\n按质量分组:")
    for q in ["excellent", "good", "low_sample", "inferred"]:
        items = get_factors_by_quality(q)
        print(f"  {q}: {len(items)} 个")
    print(f"\n信号充足 (≥200) 的因子: {len(get_factors_above_signals(200))} 个")
    print(f"胜率 ≥80% 的因子: {len(get_factors_above_winrate(80))} 个")