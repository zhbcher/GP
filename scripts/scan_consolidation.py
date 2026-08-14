#!/usr/bin/env python3
"""震荡因子扫描 - 从历史数据中挖掘震荡因子的表现"""
import sys, os, sqlite3, math, time
sys.path.append('/Users/zhoubo/GP/scripts')
import numpy as np
from collections import defaultdict

DB = "/Users/zhoubo/GP/data/stock.db"
HORIZON = 20

# 震荡参数空间
WINDOWS = [10, 20, 30, 45, 60]        # 震荡窗口（天）
WIDTHS = [0.03, 0.05, 0.08, 0.12]     # 区间宽度（比例）
MIN_DAYS = [5, 10, 15, 20]             # 最少震荡天数

# 增强方式
ENHANCEMENTS = [
    ("none", "无增强"),
    ("vol_surge", "放量突破"),
    ("rsi_low", "RSI低位"),
    ("rsi_high", "RSI高位"),
]

def load_stock_sample():
    """加载10只代表性股票做快速扫描"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY RANDOM() LIMIT 10")
    codes = [r[0] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute("SELECT close, high, low, volume, trade_date FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [dict(r) for r in cur.fetchall()]
        if len(rows) > 100:
            result[code] = rows
    conn.close()
    return result

def detect_consolidation(closes, highs, lows, window, width_ratio, min_consolidation_days):
    """检测震荡区间，返回触发信号数组"""
    n = len(closes)
    out = [False] * n
    if n < window + HORIZON:
        return out
    
    for i in range(window, n - HORIZON):
        # 最近 window 天的价格区间
        window_high = max(highs[i-window+1:i+1])
        window_low = min(lows[i-window+1:i+1])
        if window_low == 0:
            continue
        range_width = (window_high - window_low) / window_low
        
        # 条件1: 区间宽度小于阈值（横盘）
        if range_width > width_ratio:
            continue
        
        # 条件2: 连续震荡天数（最后一段在窄幅区间内的天数）
        recent_low = lows[i]
        recent_high = highs[i]
        consolidation_days = 1
        for j in range(i-1, i-window, -1):
            recent_low = min(recent_low, lows[j])
            recent_high = max(recent_high, highs[j])
            if (recent_high - recent_low) / recent_low > width_ratio if recent_low > 0 else True:
                break
            consolidation_days += 1
        
        if consolidation_days < min_consolidation_days:
            continue
        
        out[i] = True
    return out

def rsi_14(closes, i):
    if i < 14:
        return 50.0
    gains = losses = 0.0
    for j in range(i-13, i+1):
        d = closes[j] - closes[j-1]
        if d > 0: gains += d
        else: losses -= d
    avg_loss = losses / 14
    if avg_loss == 0:
        return 100.0
    rs = (gains/14) / avg_loss
    return 100 - 100 / (1 + rs)

def vol_ratio(vols, i, period=5):
    if i < period:
        return 1.0
    avg = sum(vols[i-period:i]) / period
    return vols[i] / avg if avg > 0 else 1.0

def apply_enhancement(closes, vols, idx, enh_type):
    """应用增强条件"""
    if enh_type == "none":
        return True
    if enh_type == "vol_surge":
        return vol_ratio(vols, idx) >= 1.5
    if enh_type == "rsi_low":
        return rsi_14(closes, idx) < 30
    if enh_type == "rsi_high":
        return rsi_14(closes, idx) > 70
    return True

def main():
    print("加载样本股票...", flush=True)
    stocks = load_stock_sample()
    print(f"加载 {len(stocks)} 只股票", flush=True)
    
    results = []
    total = len(WINDOWS) * len(WIDTHS) * len(MIN_DAYS) * len(ENHANCEMENTS)
    done = 0
    
    for window in WINDOWS:
        for width in WIDTHS:
            for min_days in MIN_DAYS:
                for enh_name, enh_label in ENHANCEMENTS:
                    done += 1
                    total_sig = 0
                    total_corr = 0
                    total_ret = 0.0
                    
                    for code, rows in stocks.items():
                        closes = [r['close'] for r in rows]
                        highs = [r['high'] for r in rows]
                        lows = [r['low'] for r in rows]
                        vols = [r['volume'] for r in rows]
                        
                        sigs = detect_consolidation(closes, highs, lows, window, width, min_days)
                        
                        for i in range(window, len(closes) - HORIZON):
                            if not sigs[i]:
                                continue
                            if not apply_enhancement(closes, vols, i, enh_name):
                                continue
                            if closes[i] == 0:
                                continue
                            total_sig += 1
                            ret = (closes[i+HORIZON] - closes[i]) / closes[i]
                            total_ret += ret
                            if ret > 0.005:
                                total_corr += 1
                    
                    wr = total_corr / total_sig * 100 if total_sig > 0 else 0
                    avg = total_ret / total_sig * 100 if total_sig > 0 else 0
                    results.append((window, width, min_days, enh_name, total_sig, wr, avg))
                    
                    if done % 10 == 0:
                        print(f"  [{done}/{total}]", flush=True)
    
    # 排序输出
    results.sort(key=lambda x: x[5], reverse=True)
    
    print(f"\n{'='*90}")
    print(f"  震荡因子扫描结果 (20日持有, 10只样本股票)")
    print(f"{'='*90}")
    print(f"{'窗口':>5} {'宽度':>6} {'最少天':>6} {'增强':<10} {'信号':>6} {'胜率':>7} {'均值':>7}")
    print(f"{'─'*5} {'─'*6} {'─'*6} {'─'*10} {'─'*6} {'─'*7} {'─'*7}")
    
    for r in results[:30]:
        w, wid, md, enh, sig, wr, avg = r
        print(f"{w:>5}d {wid:>5.0%} {md:>5}d {enh:<10} {sig:>6} {wr:>6.1f}% {avg:>+6.2f}%")
    
    # 按信号量过滤后的胜率
    print(f"\n{'─'*90}")
    print(f"  信号充足 (≥50) 的震荡因子")
    print(f"{'─'*90}")
    viable = [r for r in results if r[4] >= 50]
    viable.sort(key=lambda x: x[5], reverse=True)
    for r in viable[:20]:
        w, wid, md, enh, sig, wr, avg = r
        print(f"  {w:>3}d 宽{wid:>4.0%} 震荡≥{md:>2}d {enh:<10} 信号={sig:>4} 胜率={wr:>5.1f}% 均值={avg:>+6.2f}%")
    
    # 与超跌因子对比
    print(f"\n{'─'*90}")
    print(f"  对比: 超跌因子最佳表现 (同数据源)")
    print(f"{'─'*90}")
    print(f"  10d跌10%阴7 + vol_surge: 信号=606, 胜率=88.6%, 均值=+22.33%")
    print(f"  10d跌15%阴8 + rsi_strict: 信号=1896, 胜率=78.8%, 均值=+18.44%")

if __name__ == "__main__":
    main()
