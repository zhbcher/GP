#!/usr/bin/env python3
"""震荡因子系统扫描 - 多条件组合挖掘"""
import sys, os, sqlite3, math, time
sys.path.append('/Users/zhoubo/GP/scripts')
import numpy as np

DB = "/Users/zhoubo/GP/data/stock.db"
HORIZON = 20

def load_stock_sample(n=30):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY RANDOM() LIMIT ?", (n,))
    codes = [r[0] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute("SELECT close, high, low, volume, trade_date FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [{'close':r[0],'high':r[1],'low':r[2],'volume':r[3],'trade_date':r[4]} for r in cur.fetchall()]
        if len(rows) > 100: result[code] = rows
    conn.close()
    return result

def compute_features(closes, highs, lows, vols, i):
    f = {}
    for w in [10, 20, 30, 45, 60]:
        if i >= w:
            hi = max(highs[i-w+1:i+1]); lo = min(lows[i-w+1:i+1])
            f[f'range_{w}d'] = (hi - lo) / lo if lo > 0 else 0
        else: f[f'range_{w}d'] = 1.0
    if i >= 40:
        cur_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(i-9, i+1)]
        prev_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(i-29, i-10)]
        f['vol_shrink'] = np.std(cur_ret) / np.std(prev_ret) if np.std(prev_ret) > 0 else 1.0
    else: f['vol_shrink'] = 1.0
    for w in [20, 60, 120]:
        if i >= w:
            hi = max(closes[i-w+1:i+1]); lo = min(closes[i-w+1:i+1])
            f[f'pos_{w}d'] = (closes[i]-lo)/(hi-lo) if hi > lo else 0.5
        else: f[f'pos_{w}d'] = 0.5
    if i >= 20:
        recent_v = sum(vols[i-4:i+1])/5; prev_v = sum(vols[i-19:i-5])/15
        f['vol_shrink_ratio'] = recent_v / prev_v if prev_v > 0 else 1.0
    else: f['vol_shrink_ratio'] = 1.0
    for w in [10, 20, 30]:
        if i >= w:
            hi = max(highs[i-w+1:i+1]); lo = min(lows[i-w+1:i+1])
            width = (hi-lo)/lo if lo > 0 else 1
            if width < 0.08:
                f['consec_consolidation'] = w; break
            else: f['consec_consolidation'] = 0
    if i >= 20:
        hi = max(highs[i-19:i]); lo = min(lows[i-19:i])
        f['breakout_up'] = 1.0 if closes[i] > hi else 0.0
        f['breakout_down'] = 1.0 if closes[i] < lo else 0.0
    else: f['breakout_up'] = 0.0; f['breakout_down'] = 0.0
    if i >= 19:
        ma5 = sum(closes[i-4:i+1])/5; ma20 = sum(closes[i-19:i+1])/20
        f['above_ma20'] = 1.0 if closes[i] > ma20 else 0.0
        f['ma5_above_ma20'] = 1.0 if ma5 > ma20 else 0.0
    else: f['above_ma20'] = 0.0; f['ma5_above_ma20'] = 0.0
    if i >= 59:
        ma60 = sum(closes[i-59:i+1])/60; ma20 = sum(closes[i-19:i+1])/20
        f['ma20_above_ma60'] = 1.0 if ma20 > ma60 else 0.0
    else: f['ma20_above_ma60'] = 0.0
    return f

CONDITIONS = [
    ("range_20d", "lt", 0.05, "20日区间<5%"),
    ("range_20d", "lt", 0.08, "20日区间<8%"),
    ("range_30d", "lt", 0.08, "30日区间<8%"),
    ("range_45d", "lt", 0.10, "45日区间<10%"),
    ("vol_shrink", "lt", 0.5, "波动收缩50%"),
    ("vol_shrink", "lt", 0.7, "波动收缩70%"),
    ("pos_60d", "gt", 0.8, "60日高位>80%"),
    ("pos_60d", "lt", 0.2, "60日低位<20%"),
    ("pos_20d", "gt", 0.8, "20日高位>80%"),
    ("pos_20d", "lt", 0.2, "20日低位<20%"),
    ("vol_shrink_ratio", "lt", 0.6, "量能萎缩60%"),
    ("vol_shrink_ratio", "lt", 0.8, "量能萎缩80%"),
    ("vol_shrink_ratio", "gt", 1.5, "量能放大150%"),
    ("consec_consolidation", "ge", 10, "连续横盘≥10天"),
    ("consec_consolidation", "ge", 20, "连续横盘≥20天"),
    ("consec_consolidation", "ge", 30, "连续横盘≥30天"),
    ("breakout_up", "eq", 1.0, "向上突破"),
    ("breakout_down", "eq", 1.0, "向下突破"),
    ("above_ma20", "eq", 1.0, "站上MA20"),
    ("ma5_above_ma20", "eq", 1.0, "MA5>MA20"),
    ("ma20_above_ma60", "eq", 1.0, "MA20>MA60"),
]

def check(feat, fn, op, th):
    v = feat.get(fn)
    if v is None: return False
    if op == "lt": return v < th
    if op == "gt": return v > th
    if op == "ge": return v >= th
    if op == "eq": return abs(v - th) < 0.01
    return False

def main():
    stocks = load_stock_sample(30)
    print(f"Loaded {len(stocks)} stocks", flush=True)

    all_f = {}
    for code, rows in stocks.items():
        cl = [r['close'] for r in rows]; hi = [r['high'] for r in rows]
        lo = [r['low'] for r in rows]; vl = [r['volume'] for r in rows]
        feats = []
        for i in range(60, len(cl) - HORIZON):
            feats.append(compute_features(cl, hi, lo, vl, i))
        all_f[code] = (cl, feats, len(cl))

    # 单条件
    print(f"\n{'='*90}")
    print(f"  单条件扫描 (30只股票, 20日持有)")
    print(f"{'='*90}")
    print(f"{'条件':<22} {'信号':>6} {'对':>6} {'胜率':>7} {'均值':>8}")
    print(f"{'─'*22} {'─'*6} {'─'*6} {'─'*7} {'─'*8}")

    single = []
    for fn, op, th, label in CONDITIONS:
        sig = corr = 0; ret_sum = 0.0
        for code, (cl, feats, n) in all_f.items():
            for idx, feat in enumerate(feats):
                i = idx + 60
                if not check(feat, fn, op, th): continue
                if cl[i] == 0: continue
                sig += 1
                r = (cl[i+HORIZON]-cl[i])/cl[i]
                ret_sum += r
                if r > 0.005: corr += 1
        wr = corr/sig*100 if sig else 0; avg = ret_sum/sig*100 if sig else 0
        single.append((label, fn, op, th, sig, wr, avg))
        print(f"  {label:<22} {sig:>6} {corr:>6} {wr:>6.1f}% {avg:>+7.2f}%")

    # 好单条件
    print(f"\n{'─'*90}")
    print(f"  信号≥100 且 胜率≥55% 的单条件:")
    goods = [(l, s, w, a) for l,_,_,_,s,w,a in single if s>=100 and w>=55]
    goods.sort(key=lambda x: x[2], reverse=True)
    for l, s, w, a in goods:
        print(f"  {l:<22} 信号={s:>5} 胜率={w:>5.1f}% 均值={a:>+6.2f}%")

    # 双条件组合
    cands = [(l, fn, op, th) for l, fn, op, th, s, w, a in single if (s>=100 and w>=53) or w>=58]
    print(f"\n{'='*90}")
    print(f"  双条件 AND 组合 Top 20 (信号≥30)")
    print(f"{'='*90}")
    print(f"{'组合':<50} {'信号':>6} {'胜率':>7} {'均值':>8}")
    print(f"{'─'*50} {'─'*6} {'─'*7} {'─'*8}")

    combos = []
    for ci in range(len(cands)):
        for cj in range(ci+1, len(cands)):
            l1, fn1, op1, th1 = cands[ci]; l2, fn2, op2, th2 = cands[cj]
            sig = corr = 0; ret_sum = 0.0
            for code, (cl, feats, n) in all_f.items():
                for idx, feat in enumerate(feats):
                    i = idx + 60
                    if not (check(feat, fn1, op1, th1) and check(feat, fn2, op2, th2)): continue
                    if cl[i] == 0: continue
                    sig += 1; r = (cl[i+HORIZON]-cl[i])/cl[i]; ret_sum += r
                    if r > 0.005: corr += 1
            wr = corr/sig*100 if sig else 0; avg = ret_sum/sig*100 if sig else 0
            combos.append((f"{l1}+{l2}", sig, wr, avg))

    combos.sort(key=lambda x: x[2], reverse=True)
    for label, s, w, a in combos[:20]:
        if s >= 30:
            print(f"  {label:<50} {s:>6} {w:>6.1f}% {a:>+7.2f}%")

    # 三条件组合 (用最好的2-3个单条件)
    print(f"\n{'='*90}")
    print(f"  三条件 AND 组合 (用胜率最高的单条件)")
    print(f"{'='*90}")
    top3 = [c for c in cands if any(l in c[0] for l in ['向上突破','连续横盘','波动收缩','低位'])]
    top3 = top3[:5]
    combos3 = []
    for ci in range(len(top3)):
        for cj in range(ci+1, len(top3)):
            for ck in range(cj+1, len(top3)):
                l1, fn1, o1, t1 = top3[ci]; l2, fn2, o2, t2 = top3[cj]; l3, fn3, o3, t3 = top3[ck]
                sig = corr = 0; ret_sum = 0.0
                for code, (cl, feats, n) in all_f.items():
                    for idx, feat in enumerate(feats):
                        i = idx + 60
                        if not (check(feat,fn1,o1,t1) and check(feat,fn2,o2,t2) and check(feat,fn3,o3,t3)): continue
                        if cl[i]==0: continue
                        sig += 1; r = (cl[i+HORIZON]-cl[i])/cl[i]; ret_sum += r
                        if r > 0.005: corr += 1
                wr = corr/sig*100 if sig else 0; avg = ret_sum/sig*100 if sig else 0
                combos3.append((f"{l1}+{l2}+{l3}", sig, wr, avg))
    combos3.sort(key=lambda x: x[2], reverse=True)
    for label, s, w, a in combos3[:15]:
        if s >= 10:
            print(f"  {label:<60} {s:>5} {w:>5.1f}% {a:>+6.2f}%")

if __name__ == "__main__":
    main()
