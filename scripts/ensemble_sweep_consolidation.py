#!/usr/bin/env python3
"""震荡增强版集成投票扫描"""
import sys, os, json, glob, time, sqlite3
import numpy as np
import xgboost as xgb
import joblib
sys.path.append('/Users/zhoubo/GP/scripts')
from factors import BASE_FACTORS, BOOST_TYPES
import train_factors_consolidation as TFC

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MODEL_DIR = "/Users/zhoubo/GP/scripts/trained_models_consolidation"
HORIZON = 20

def load_stocks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code")
    codes = [r[0] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute("SELECT trade_date, open, high, low, close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [{'trade_date':r[0],'open':r[1],'high':r[2],'low':r[3],'close':r[4],'volume':r[5]} for r in cur.fetchall()]
        if len(rows) > 80: result[code] = rows
    conn.close()
    return result

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
            if bf: models_info.append((bf, boost, model, label))
            break
print(f"Loaded {len(models_info)} models", flush=True)

# 预计算
print("Precomputing...", flush=True)
stock_data = {}
t0 = time.time()
for ci, (code, rows) in enumerate(stocks.items()):
    if ci % 300 == 0: print(f"  [{ci}/{len(stocks)}] {time.time()-t0:.0f}s", flush=True)
    closes = [r['close'] for r in rows]; highs = [r['high'] for r in rows]
    lows = [r['low'] for r in rows]; vols = [r['volume'] for r in rows]
    n = len(closes); test_start = 60 + int((n - 60 - 20) * 0.7)

    # 预计算特征向量
    fvs = []
    for i in range(test_start, n - 20):
        try:
            base = TFC.base_features(closes, highs, lows, vols, i)
            consol = TFC.consolidation_features(closes, highs, lows, vols, i)
            fvs.append(TFC.make_feature_vector(base, consol))
        except: fvs.append(None)

    model_sigs = []
    for bf, boost, model, _ in models_info:
        sigs = TFC.oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost)
        model_sigs.append(sigs[test_start:n-20])

    model_preds = []
    for mi, (bf, boost, model, _) in enumerate(models_info):
        preds = []
        for j, fv_ in enumerate(fvs):
            if fv_ is not None and model_sigs[mi][j]:
                prob = model.predict_proba(fv_.reshape(1, -1))[0]
                preds.append(1 if len(prob) > 1 and prob[1] >= 0.5 else 0)
            else: preds.append(0)
        model_preds.append(preds)

    stock_data[code] = {'closes': closes[test_start:n-20], 'preds': model_preds, 'n_days': len(fvs)}

print(f"Precompute done in {time.time()-t0:.0f}s", flush=True)

# 扫描
print(f"\n{'='*70}", flush=True)
print(f"  震荡增强版集成投票 ({len(models_info)} 个模型)", flush=True)
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
                else: ret = 0
                total_sum += ret
                if ret > 0.005: total_corr += 1
    wr = total_corr / total_sig * 100 if total_sig else 0
    avg = total_sum / total_sig * 100 if total_sig else 0
    weekly = total_sig / 5000 * 5 if total_sig > 0 else 0
    mark = " ◀◀" if wr >= 70 and total_sig >= 500 else ""
    print(f"  {f'{threshold}/{len(models_info)}':>10} {total_sig:>8} {total_corr:>6} {wr:>6.1f}% {avg:>+6.2f}% {weekly:>5.0f}{mark}", flush=True)
    best.append((threshold, total_sig, total_corr, wr, avg, weekly))

viable = [(t, s, w, a, wk) for t, s, _, w, a, wk in best if w >= 70 and s >= 300]
if viable:
    best_balance = max(viable, key=lambda x: x[1]*x[2])
    best_sig = max(viable, key=lambda x: x[1])
    best_wr = max(viable, key=lambda x: x[2])
    print(f"\n  ★ 震荡增强版最优:", flush=True)
    print(f"    最多信号: {best_sig[0]}/{len(models_info)}, 信号={best_sig[1]}, 胜率={best_sig[2]:.1f}%, 周均={best_sig[4]:.0f}", flush=True)
    print(f"    最高胜率: {best_wr[0]}/{len(models_info)}, 信号={best_wr[1]}, 胜率={best_wr[2]:.1f}%, 周均={best_wr[4]:.0f}", flush=True)
    print(f"    最佳平衡: {best_balance[0]}/{len(models_info)}, 信号={best_balance[1]}, 胜率={best_balance[2]:.1f}%, 周均={best_balance[4]:.0f}", flush=True)

report = {'data': {'stocks': len(stocks), 'horizon': 20, 'models': len(models_info)},
          'ensemble': [{'threshold': t, 'signals': s, 'correct': c, 'win_rate': round(w,1), 'avg_return': round(a,2), 'weekly_est': round(wk)} for t,s,c,w,a,wk in best]}
with open(os.path.join(MODEL_DIR, 'ensemble_report.json'), 'w') as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"\n  Report saved", flush=True)
