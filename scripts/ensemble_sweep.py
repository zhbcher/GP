#!/usr/bin/env python3
"""全市场集成投票扫描 - 独立脚本（不依赖train_factors）"""
import sys, os, json, pickle, glob, time, sqlite3, math
import numpy as np
import xgboost as xgb
import joblib

from factors import FACTORS_70_PLUS, BASE_FACTORS, BOOST_TYPES

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MODEL_DIR = "/Users/zhoubo/GP/scripts/trained_models_consolidation"
HORIZON = 20

# ====== Feature (copied from train_factors) ======
def compute_features(closes, highs, lows, volumes, idx):
    f = {}
    for p in [1, 3, 5, 10, 20]:
        if idx >= p and closes[idx-p] > 0:
            f[f'ret_{p}d'] = (closes[idx] - closes[idx-p]) / closes[idx-p]
        else:
            f[f'ret_{p}d'] = 0.0
    for p in [5, 10, 20, 30, 60]:
        if idx >= p-1:
            ma = sum(closes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'ma_{p}_ratio'] = closes[idx] / ma if ma > 0 else 1.0
        else:
            f[f'ma_{p}_ratio'] = 1.0
    if idx >= 14:
        gains = losses = 0.0
        for j in range(idx-13, idx+1):
            d = closes[j] - closes[j-1]
            if d > 0: gains += d
            else: losses -= d
        avg_loss = losses / 14
        rs = (gains/14) / avg_loss if avg_loss > 0 else 999
        f['rsi_14'] = 100 - 100 / (1 + rs)
    else:
        f['rsi_14'] = 50.0
    for p in [5, 20]:
        if idx >= p:
            avg_v = sum(volumes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'vol_ratio_{p}'] = volumes[idx] / avg_v if avg_v > 0 else 1.0
        else:
            f[f'vol_ratio_{p}'] = 1.0
    for p in [5, 10, 20]:
        if idx >= p:
            rets = []
            for j in range(idx-p+1, idx+1):
                if closes[j-1] == 0:
                    rets.append(0.0)
                else:
                    rets.append(closes[j] / closes[j-1] - 1)
            f[f'vol_{p}d'] = np.std(rets) if len(rets) > 1 else 0.0
        else:
            f[f'vol_{p}d'] = 0.0
    for p in [20, 60]:
        if idx >= p:
            lo = min(closes[idx-p:idx+1]); hi = max(closes[idx-p:idx+1])
            f[f'pos_{p}d'] = (closes[idx] - lo) / (hi - lo) if hi > lo else 0.5
        else:
            f[f'pos_{p}d'] = 0.5
    if idx >= 14:
        trs = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(idx-13, idx+1)]
        atr = sum(trs) / 14
        f['atr_ratio'] = (highs[idx] - lows[idx]) / atr if atr > 0 else 1.0
    else:
        f['atr_ratio'] = 1.0
    down = 0
    for j in range(idx, max(0, idx-10), -1):
        if j >= 1 and closes[j] < closes[j-1]:
            down += 1
        else:
            break
    f['consec_down'] = down
    for p in [10, 20, 60]:
        if idx >= p:
            peak = max(closes[idx-p:idx+1])
            f[f'oversold_{p}'] = (closes[idx] - peak) / peak if peak > 0 else 0.0
        else:
            f[f'oversold_{p}'] = 0.0
    return f

FEATURE_NAMES = ['ret_1d','ret_3d','ret_5d','ret_10d','ret_20d',
    'ma_5_ratio','ma_10_ratio','ma_20_ratio','ma_30_ratio','ma_60_ratio',
    'rsi_14','vol_ratio_5','vol_ratio_20','vol_5d','vol_10d','vol_20d',
    'pos_20d','pos_60d','atr_ratio','consec_down',
    'oversold_10','oversold_20','oversold_60']

def fv(f_dict):
    return np.array([f_dict.get(k, 0.0) for k in FEATURE_NAMES], dtype=np.float64)

def oversold_signals(rows, days, drop_pct, consec_down, boost_type):
    closes = [r['close'] for r in rows]
    vols = [r['volume'] for r in rows]
    n = len(closes)
    out = [False] * n
    for i in range(days, n):
        if closes[i-days] <= 0: continue
        ret = (closes[i] - closes[i-days]) / closes[i-days]
        if ret >= -drop_pct / 100.0: continue
        down_count = 0
        for j in range(i, i-days, -1):
            if j <= 0: break
            if closes[j] < closes[j-1]: down_count += 1
            else: break
        if down_count < consec_down: continue
        if boost_type == "no_boost" or boost_type == "loose":
            out[i] = True
        elif boost_type == "rsi_strict":
            if i < 14: continue
            gains = losses = 0.0
            for j in range(i-13, i+1):
                d = closes[j] - closes[j-1]
                if d > 0: gains += d
                else: losses -= d
            rsi = 100 - 100 / (1 + (gains/14)/(losses/14)) if losses > 0 else 100.0
            if rsi < 30: out[i] = True
        elif boost_type == "vol_surge":
            if i < 6: continue
            avg_v = sum(vols[i-5:i]) / 5
            if avg_v > 0 and vols[i] >= 2.0 * avg_v: out[i] = True
    return out

def load_stocks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code")
    codes = [r["stock_code"] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute("SELECT trade_date, open, high, low, close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [dict(r) for r in cur.fetchall()]
        if len(rows) > 80:
            result[code] = rows
    conn.close()
    return result

# ====== Main ======
print("Loading stocks...", flush=True)
stocks = load_stocks()
print(f"Loaded {len(stocks)} stocks", flush=True)

model_files = sorted(glob.glob(os.path.join(MODEL_DIR, "best_model_*.joblib")))
models_info = []
for mf in model_files:
    label = os.path.basename(mf).replace("best_model_", "").replace(".joblib", "")
    model = joblib.load(mf)
    for boost in BOOST_TYPES:
        suffix = f"_{boost}"
        if label.endswith(suffix):
            fac_name = label[:-len(suffix)]
            bf = next((b for b in BASE_FACTORS if b['name'] == fac_name), None)
            if bf:
                models_info.append((bf, boost, model, label))
            break
print(f"Loaded {len(models_info)} models", flush=True)

# Precompute
print("Precomputing features & signals...", flush=True)
stock_data = {}
t0 = time.time()
for ci, (code, rows) in enumerate(stocks.items()):
    if ci % 300 == 0:
        print(f"  [{ci}/{len(stocks)}] {time.time()-t0:.0f}s", flush=True)
    closes = [r['close'] for r in rows]
    highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows]
    vols = [r['volume'] for r in rows]
    n = len(closes)
    test_start = 60 + int((n - 60 - 20) * 0.7)

    fvs = []
    for i in range(test_start, n - 20):
        feat = compute_features(closes, highs, lows, vols, i)
        fvs.append(fv(feat))

    model_sigs = []
    for bf, boost, model, _ in models_info:
        sigs = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost)
        model_sigs.append(sigs[test_start:n-20])

    model_preds = []
    for mi, (bf, boost, model, _) in enumerate(models_info):
        preds = []
        for j, fv_ in enumerate(fvs):
            if model_sigs[mi][j]:
                prob = model.predict_proba(fv_.reshape(1, -1))[0]
                preds.append(1 if len(prob) > 1 and prob[1] >= 0.5 else 0)
            else:
                preds.append(0)
        model_preds.append(preds)

    stock_data[code] = {'closes': closes[test_start:n-20], 'preds': model_preds, 'n_days': len(fvs)}

print(f"Precompute done in {time.time()-t0:.0f}s", flush=True)

# Sweep
print(f"\n{'='*70}", flush=True)
print(f"  全市场集成投票 ({len(models_info)} 个模型)", flush=True)
print(f"{'='*70}", flush=True)
print(f"{'阈值':>10} {'信号':>8} {'对':>6} {'胜率':>7} {'均值':>7} {'周均':>6}", flush=True)
print(f"{'─'*10} {'─'*8} {'─'*6} {'─'*7} {'─'*7} {'─'*6}", flush=True)

best = []
for threshold in range(1, len(models_info) + 1):
    total_sig = 0; total_corr = 0; total_sum = 0.0
    for code, sd in stock_data.items():
        for j in range(sd['n_days']):
            votes = sum(sd['preds'][mi][j] for mi in range(len(models_info)))
            if votes >= threshold:
                total_sig += 1
                if j+20 < len(sd['closes']) and sd['closes'][j] != 0:
                    ret = (sd['closes'][j+20] - sd['closes'][j]) / sd['closes'][j]
                else:
                    ret = 0
                total_sum += ret
                if ret > 0.005:
                    total_corr += 1
    wr = total_corr / total_sig * 100 if total_sig else 0
    avg = total_sum / total_sig * 100 if total_sig else 0
    weekly = total_sig / 5000 * 5 if total_sig > 0 else 0
    mark = " ◀◀" if wr >= 70 and total_sig >= 500 else ""
    print(f"  {f'{threshold}/{len(models_info)}':>10} {total_sig:>8} {total_corr:>6} {wr:>6.1f}% {avg:>+6.2f}% {weekly:>5.0f}{mark}", flush=True)
    best.append((threshold, total_sig, total_corr, wr, avg, weekly))

viable = [(t, s, w, a, wk) for t, s, _, w, a, wk in best if w >= 70 and s >= 300]
if viable:
    best_balance = max(viable, key=lambda x: x[1] * x[2])
    best_sig = max(viable, key=lambda x: x[1])
    best_wr = max(viable, key=lambda x: x[2])
    print(f"\n{'='*70}", flush=True)
    print(f"  ★ 全市场最优方案", flush=True)
    print(f"{'='*70}", flush=True)
    print(f"  最多信号: 阈值 {best_sig[0]}/{len(models_info)}, 信号={best_sig[1]}, 胜率={best_sig[2]:.1f}%, 周均={best_sig[4]:.0f}信号", flush=True)
    print(f"  最高胜率: 阈值 {best_wr[0]}/{len(models_info)}, 信号={best_wr[1]}, 胜率={best_wr[2]:.1f}%, 周均={best_wr[4]:.0f}信号", flush=True)
    print(f"  最佳平衡: 阈值 {best_balance[0]}/{len(models_info)}, 信号={best_balance[1]}, 胜率={best_balance[2]:.1f}%, 周均={best_balance[4]:.0f}信号", flush=True)

report = {'data': {'stocks': len(stocks), 'horizon': 20, 'models': len(models_info)},
          'ensemble': [{'threshold': t, 'signals': s, 'correct': c, 'win_rate': round(w,1), 'avg_return': round(a,2), 'weekly_est': round(wk)} for t,s,c,w,a,wk in best]}
with open(os.path.join(MODEL_DIR, 'pipeline_report.json'), 'w') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n  Report saved", flush=True)
