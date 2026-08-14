#!/usr/bin/env python3
"""
OR 因子组合回测工具
用法: cd ~/GP && python3 scripts/or_backtest.py
"""

import math, sqlite3
from collections import defaultdict

DB_PATH = "/Users/zhoubo/GP/data/stock.db"

FACTORS = [
    {"type": "rsi_below", "threshold": 30},
    {"type": "rsi_below", "threshold": 35},
    {"type": "rsi_below", "threshold": 40},
    {"type": "rsi_above", "threshold": 70},
    {"type": "rsi_above", "threshold": 75},
    {"type": "rsi_above", "threshold": 80},
    {"type": "macd_cross_up"},
    {"type": "macd_cross_down"},
    {"type": "dif_above_dea"},
    {"type": "dif_below_dea"},
    {"type": "boll_touch_lower"},
    {"type": "boll_break_upper"},
    {"type": "boll_squeeze"},
    {"type": "vol_surge", "multiplier": 2.0},
    {"type": "vol_surge", "multiplier": 3.0},
    {"type": "vol_surge", "multiplier": 5.0},
    {"type": "close_above_ma5_ma20"},
    {"type": "ma5_cross_above_ma20"},
    {"type": "ma5_cross_below_ma20"},
    {"type": "return_5d_pos"},
    {"type": "return_5d_neg"},
]

HORIZON = 5
DIRECTION_THRESHOLD = 0.005
MIN_DATA = 50


def ema(arr, period):
    k = 2.0 / (period + 1)
    out = [0.0] * len(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = arr[i] * k + out[i - 1] * (1 - k)
    return out


def precompute(closes, vols):
    n = len(closes)
    r = {}

    # MA
    for p in [5, 20]:
        r[f"ma{p}"] = [sum(closes[max(0,i-p+1):i+1]) / min(p, i+1) for i in range(n)]

    # MACD
    dif = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    r["dif"], r["dea"] = dif, ema(dif, 9)

    # RSI
    rsi = [50.0] * n
    for i in range(14, n):
        w = l = 0
        for j in range(i-13, i+1):
            d = closes[j] - closes[j-1]
            if d > 0: w += d
            else: l -= d
        rsi[i] = 100 - 100 / (1 + w / l) if l else 100.0
    r["rsi"] = rsi

    # Bollinger
    bl, bu, bm, bs = [], [], [], []
    for i in range(n):
        if i < 19:
            bl.append(0); bu.append(0); bm.append(0); bs.append(0)
        else:
            w = closes[i-19:i+1]
            m = sum(w) / 20
            s = math.sqrt(sum((c-m)**2 for c in w) / 20)
            bl.append(m - 2*s); bu.append(m + 2*s); bm.append(m); bs.append(s)
    r["bl"], r["bu"], r["bm"], r["bs"] = bl, bu, bm, bs

    # Volume ratio
    vr = []
    for i in range(n):
        if i < 5: vr.append(1.0)
        else:
            avg = sum(vols[i-5:i]) / 5
            vr.append(vols[i] / avg if avg > 0 else 1.0)
    r["vr"] = vr

    # Returns
    r5 = []
    for i in range(n):
        if i < 5 or closes[i-5] == 0: r5.append(0)
        else: r5.append((closes[i] - closes[i-5]) / closes[i-5])
    r["r5"] = r5

    # BW (Bollinger width) for squeeze
    bw = []
    for i in range(n):
        if bm[i] > 0: bw.append((bu[i] - bl[i]) / bm[i])
        else: bw.append(0)
    r["bw"] = bw

    return r


def check(ic, closes, idx, factor):
    t = factor["type"]
    if t == "rsi_below":
        return ic["rsi"][idx] < factor.get("threshold", 30), "up"
    if t == "rsi_above":
        return ic["rsi"][idx] > factor.get("threshold", 70), "down"
    if t == "macd_cross_up" and idx >= 1:
        if ic["dif"][idx-1] < ic["dea"][idx-1] and ic["dif"][idx] >= ic["dea"][idx]:
            return True, "up"
    if t == "macd_cross_down" and idx >= 1:
        if ic["dif"][idx-1] > ic["dea"][idx-1] and ic["dif"][idx] <= ic["dea"][idx]:
            return True, "down"
    if t == "dif_above_dea":
        return ic["dif"][idx] > ic["dea"][idx], "up"
    if t == "dif_below_dea":
        return ic["dif"][idx] < ic["dea"][idx], "down"
    if t == "boll_touch_lower":
        if ic["bl"][idx] > 0 and closes[idx] <= ic["bl"][idx]:
            return True, "up"
    if t == "boll_break_upper" and idx >= 1:
        if closes[idx-1] >= ic["bu"][idx-1] and closes[idx] < ic["bu"][idx]:
            return True, "down"
    if t == "boll_squeeze" and idx >= 40:
        if ic["bw"][idx-20] > 0 and ic["bw"][idx] < ic["bw"][idx-20] * 0.5:
            return True, "up"
    if t == "vol_surge":
        m = factor.get("multiplier", 2.0)
        return ic["vr"][idx] >= m, "up"
    if t == "close_above_ma5_ma20":
        return closes[idx] > ic["ma5"][idx] > ic["ma20"][idx], "up"
    if t == "ma5_cross_above_ma20" and idx >= 1:
        if ic["ma5"][idx-1] <= ic["ma20"][idx-1] and ic["ma5"][idx] > ic["ma20"][idx]:
            return True, "up"
    if t == "ma5_cross_below_ma20" and idx >= 1:
        if ic["ma5"][idx-1] >= ic["ma20"][idx-1] and ic["ma5"][idx] < ic["ma20"][idx]:
            return True, "down"
    if t == "return_5d_pos":
        return ic["r5"][idx] > 0, "up"
    if t == "return_5d_neg":
        return ic["r5"][idx] < 0, "down"
    return False, None


def run_backtest(stocks):
    per_factor = defaultdict(lambda: {"triggers": 0, "correct": 0})
    or_stats = {"triggers": 0, "correct": 0}
    layer_stats = defaultdict(lambda: {"triggers": 0, "correct": 0})

    for code, rows in stocks.items():
        closes = [r["close"] for r in rows]
        vols = [r["volume"] or 0 for r in rows]
        ic = precompute(closes, vols)
        n = len(closes)

        for idx in range(MIN_DATA, n - HORIZON):
            raw = (closes[idx + HORIZON] - closes[idx]) / closes[idx]
            if abs(raw) < DIRECTION_THRESHOLD:
                continue
            actual_up = raw > 0

            hits = []
            for f in FACTORS:
                triggered, direction = check(ic, closes, idx, f)
                if triggered:
                    hits.append((f["type"], direction))

            if not hits:
                continue

            or_stats["triggers"] += 1
            up_votes = sum(1 for _, d in hits if d == "up")
            or_correct = actual_up if up_votes >= len(hits) / 2 else not actual_up
            if or_correct:
                or_stats["correct"] += 1

            lk = len(hits)
            layer_stats[lk]["triggers"] += 1
            if or_correct:
                layer_stats[lk]["correct"] += 1

            for fname, direction in hits:
                per_factor[fname]["triggers"] += 1
                if (direction == "up" and actual_up) or (direction == "down" and not actual_up):
                    per_factor[fname]["correct"] += 1

    return per_factor, or_stats, layer_stats


def print_report(pf, ostats, lstats):
    print(f"\n{'='*65}")
    print(f"  OR 因子回测报告 (horizon={HORIZON}日)")
    print(f"{'='*65}")

    print(f"\n{'─'*65}")
    print(f"  各因子单独回测 (按触发次数降序)")
    print(f"{'─'*65}")
    print(f"{'因子':<28} {'触发':>6} {'正确':>6} {'胜率':>7}")
    print(f"{'─'*28} {'─'*6} {'─'*6} {'─'*7}")

    tt = tc = 0
    for name, s in sorted(pf.items(), key=lambda x: x[1]["triggers"], reverse=True):
        wr = s["correct"] / s["triggers"] * 100 if s["triggers"] else 0
        print(f"{name:<28} {s['triggers']:>6} {s['correct']:>6} {wr:>6.1f}%")
        tt += s["triggers"]; tc += s["correct"]

    print(f"{'─'*28} {'─'*6} {'─'*6} {'─'*7}")
    avg_wr = tc / tt * 100 if tt else 0
    print(f"{'合计':<28} {tt:>6} {tc:>6} {avg_wr:>6.1f}%")

    print(f"\n{'─'*65}")
    print(f"  OR 组合 (任一因子触发 = 1次信号)")
    print(f"{'─'*65}")
    or_wr = ostats["correct"] / ostats["triggers"] * 100 if ostats["triggers"] else 0
    print(f"  信号数: {ostats['triggers']}  正确: {ostats['correct']}  胜率: {or_wr:.1f}%")

    print(f"\n{'─'*65}")
    print(f"  ★ 分层分析: 按同时触发因子数")
    print(f"{'─'*65}")
    print(f"{'因子数':>6} {'触发':>6} {'正确':>6} {'胜率':>7} {'vs均值':>8}")
    for lk in sorted(lstats):
        s = lstats[lk]
        if s["triggers"] < 20:
            continue
        wr = s["correct"] / s["triggers"] * 100
        diff = wr - avg_wr
        mark = " ◀◀ 最佳" if diff > 3 else (" ★" if diff > 1 else "")
        print(f"{lk:>6} {s['triggers']:>6} {s['correct']:>6} {wr:>6.1f}% {diff:>+7.1f}%{mark}")

    print(f"\n{'─'*65}")
    print(f"  结论: OR 胜率 {or_wr:.1f}%")
    if or_wr > 60:
        print(f"  ✅ 表现优秀")
    elif or_wr > 55:
        print(f"  ⚠️ 略高于随机，建议用分层过滤")
    else:
        print(f"  ❌ 接近随机，需要剔除低质量因子")
    print(f"  建议: 查看上面分层，找胜率最高且样本充足的那一层")
    print(f"  用 '≥ N 因子同时触发' 代替纯 OR\n{'='*65}\n")


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT stock_code FROM watchlist ORDER BY id")
    codes = [r["stock_code"] for r in cur.fetchall()]
    stocks = {}
    for code in codes:
        cur.execute("SELECT close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = cur.fetchall()
        if len(rows) > MIN_DATA + HORIZON:
            stocks[code] = rows
    conn.close()
    print(f"Loaded {len(stocks)} stocks")
    pf, os_, ls = run_backtest(stocks)
    print_report(pf, os_, ls)


if __name__ == "__main__":
    main()