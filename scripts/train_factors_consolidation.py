#!/usr/bin/env python3
"""
震荡因子增强版训练 — 在现有超跌特征基础上加入震荡特征
原 26 个模型不动，这个版本单独训练，输出到震荡模型目录
"""
import json, os, sys, sqlite3, time
import numpy as np
import xgboost as xgb
import joblib

sys.path.insert(0, '/Users/zhoubo/GP/scripts')
from factors import FACTORS_70_PLUS, BASE_FACTORS, BOOST_TYPES

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MODEL_DIR = "/Users/zhoubo/GP/scripts/trained_models_consolidation"
REPORT_PATH = os.path.join(MODEL_DIR, "pipeline_report.json")
os.makedirs(MODEL_DIR, exist_ok=True)

HORIZON = 20
LOOKBACK = 60
MIN_SAMPLES = 50

# ====== 原特征（与 train_factors.py 完全一致） ======
def base_features(closes, highs, lows, volumes, idx):
    f = {}
    for p in [1, 3, 5, 10, 20]:
        if idx >= p and closes[idx-p] > 0: f[f'ret_{p}d'] = (closes[idx] - closes[idx-p]) / closes[idx-p]
        else: f[f'ret_{p}d'] = 0.0
    for p in [5, 10, 20, 30, 60]:
        if idx >= p-1:
            ma = sum(closes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'ma_{p}_ratio'] = closes[idx] / ma if ma > 0 else 1.0
        else: f[f'ma_{p}_ratio'] = 1.0
    if idx >= 14:
        gains = losses = 0.0
        for i in range(idx-13, idx+1):
            d = closes[i] - closes[i-1]
            if d > 0: gains += d
            else: losses -= d
        rs = (gains/14) / (losses/14) if losses > 0 else 999
        f['rsi_14'] = 100 - 100 / (1 + rs)
    else: f['rsi_14'] = 50.0
    for p in [5, 20]:
        if idx >= p:
            avg_v = sum(volumes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'vol_ratio_{p}'] = volumes[idx] / avg_v if avg_v > 0 else 1.0
        else: f[f'vol_ratio_{p}'] = 1.0
    for p in [5, 10, 20]:
        if idx >= p:
            rets = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(idx-p+1, idx+1)]
            f[f'vol_{p}d'] = np.std(rets) if len(rets) > 1 else 0.0
        else: f[f'vol_{p}d'] = 0.0
    for p in [20, 60]:
        if idx >= p:
            lo = min(closes[idx-p:idx+1]); hi = max(closes[idx-p:idx+1])
            f[f'pos_{p}d'] = (closes[idx] - lo) / (hi - lo) if hi > lo else 0.5
        else: f[f'pos_{p}d'] = 0.5
    if idx >= 14:
        trs = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(idx-13, idx+1)]
        atr = sum(trs) / 14
        f['atr_ratio'] = (highs[idx] - lows[idx]) / atr if atr > 0 else 1.0
    else: f['atr_ratio'] = 1.0
    down = 0
    for j in range(idx, max(0, idx-10), -1):
        if j >= 1 and closes[j] < closes[j-1]: down += 1
        else: break
    f['consec_down'] = down
    for p in [10, 20, 60]:
        if idx >= p:
            peak = max(closes[idx-p:idx+1])
            f[f'oversold_{p}'] = (closes[idx] - peak) / peak if peak > 0 else 0.0
        else: f[f'oversold_{p}'] = 0.0
    return f

# ====== 震荡特征（新增） ======
def consolidation_features(closes, highs, lows, volumes, idx):
    """只在超跌触发时额外计算的震荡特征"""
    f = {}
    # 区间宽度 - 多窗口
    for w in [10, 20, 30, 45, 60]:
        if idx >= w:
            hi = max(highs[idx-w+1:idx+1]); lo = min(lows[idx-w+1:idx+1])
            f[f'consol_range_{w}d'] = (hi - lo) / lo if lo > 0 else 0
        else: f[f'consol_range_{w}d'] = 1.0
    
    # 波动收缩比
    if idx >= 40:
        cur_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(idx-9, idx+1)]
        prev_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(idx-29, idx-10)]
        f['consol_vol_shrink'] = np.std(cur_ret) / np.std(prev_ret) if np.std(prev_ret) > 0 else 1.0
    else: f['consol_vol_shrink'] = 1.0
    
    # 位置 - 距离历史高低点
    for w in [20, 60, 120]:
        if idx >= w:
            hi = max(closes[idx-w+1:idx+1]); lo = min(closes[idx-w+1:idx+1])
            f[f'consol_pos_{w}d'] = (closes[idx]-lo)/(hi-lo) if hi > lo else 0.5
        else: f[f'consol_pos_{w}d'] = 0.5
    
    # 量能萎缩比
    if idx >= 20:
        recent_v = sum(volumes[idx-4:idx+1])/5
        prev_v = sum(volumes[idx-19:idx-5])/15
        f['consol_vol_shrink_ratio'] = recent_v / prev_v if prev_v > 0 else 1.0
    else: f['consol_vol_shrink_ratio'] = 1.0
    
    # 连续横盘天数
    consec = 0
    for w in [10, 20, 30]:
        if idx >= w:
            hi = max(highs[idx-w+1:idx+1]); lo = min(lows[idx-w+1:idx+1])
            width = (hi-lo)/lo if lo > 0 else 1
            if width < 0.08:
                consec = w; break
    f['consol_consec_days'] = consec
    
    # 突破信号
    if idx >= 20:
        hi = max(highs[idx-19:idx]); lo = min(lows[idx-19:idx])
        f['consol_breakout_up'] = 1.0 if closes[idx] > hi else 0.0
        f['consol_breakout_down'] = 1.0 if closes[idx] < lo else 0.0
    else: f['consol_breakout_up'] = 0.0; f['consol_breakout_down'] = 0.0
    
    # 均线状态
    if idx >= 19:
        ma5 = sum(closes[idx-4:idx+1])/5; ma20 = sum(closes[idx-19:idx+1])/20
        f['consol_above_ma20'] = 1.0 if closes[idx] > ma20 else 0.0
        f['consol_ma5_above_ma20'] = 1.0 if ma5 > ma20 else 0.0
    else: f['consol_above_ma20'] = 0.0; f['consol_ma5_above_ma20'] = 0.0
    if idx >= 59:
        ma60 = sum(closes[idx-59:idx+1])/60
        ma20 = sum(closes[idx-19:idx+1])/20
        f['consol_ma20_above_ma60'] = 1.0 if ma20 > ma60 else 0.0
    else: f['consol_ma20_above_ma60'] = 0.0
    
    return f

# 特征名列表（原 + 震荡）
BASE_FEATURE_NAMES = [
    'ret_1d','ret_3d','ret_5d','ret_10d','ret_20d',
    'ma_5_ratio','ma_10_ratio','ma_20_ratio','ma_30_ratio','ma_60_ratio',
    'rsi_14',
    'vol_ratio_5','vol_ratio_20',
    'vol_5d','vol_10d','vol_20d',
    'pos_20d','pos_60d',
    'atr_ratio','consec_down',
    'oversold_10','oversold_20','oversold_60',
]

CONSOL_FEATURE_NAMES = [
    'consol_range_10d','consol_range_20d','consol_range_30d','consol_range_45d','consol_range_60d',
    'consol_vol_shrink',
    'consol_pos_20d','consol_pos_60d','consol_pos_120d',
    'consol_vol_shrink_ratio',
    'consol_consec_days',
    'consol_breakout_up','consol_breakout_down',
    'consol_above_ma20','consol_ma5_above_ma20','consol_ma20_above_ma60',
]

ALL_FEATURE_NAMES = BASE_FEATURE_NAMES + CONSOL_FEATURE_NAMES

def make_feature_vector(base_dict, consol_dict):
    vec = [base_dict.get(k, 0.0) for k in BASE_FEATURE_NAMES]
    vec += [consol_dict.get(k, 0.0) for k in CONSOL_FEATURE_NAMES]
    return np.array(vec, dtype=np.float64)

# ====== 数据加载 ======
def load_stocks():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code")
    codes = [r[0] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute("SELECT trade_date, open, high, low, close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [{'trade_date':r[0],'open':r[1],'high':r[2],'low':r[3],'close':r[4],'volume':r[5]} for r in cur.fetchall()]
        if len(rows) > LOOKBACK + HORIZON:
            result[code] = rows
    conn.close()
    return result

# ====== 超跌信号 ======
def oversold_signals(rows, days, drop_pct, consec_down, boost_type):
    closes = [r['close'] for r in rows]
    vols = [r['volume'] for r in rows]
    n = len(closes); out = [False] * n
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
        if boost_type == "no_boost" or boost_type == "loose": out[i] = True
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

# ====== 训练 ======
def build_dataset(stocks, bf, boost_type):
    X, y = [], []
    for code, rows in stocks.items():
        closes = [r['close'] for r in rows]; highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]; vols = [r['volume'] for r in rows]
        n = len(closes)
        signals = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost_type)
        for i in range(LOOKBACK, n - HORIZON):
            if not signals[i]: continue
            if closes[i] == 0: continue
            try:
                base = base_features(closes, highs, lows, vols, i)
                consol = consolidation_features(closes, highs, lows, vols, i)
            except: continue
            ret = (closes[i+HORIZON] - closes[i]) / closes[i]
            if ret > 0.02: label = 1
            elif ret < -0.02: label = 0
            else: continue
            X.append(make_feature_vector(base, consol))
            y.append(label)
    if len(X) < MIN_SAMPLES: return None, None
    return np.array(X), np.array(y)

def train_model(X, y):
    n = len(X); split = int(n * 0.7)
    model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42, subsample=0.8, use_label_encoder=False, eval_metric='logloss', verbosity=0)
    model.fit(X[:split], y[:split])
    from sklearn.metrics import accuracy_score
    train_acc = accuracy_score(y[:split], model.predict(X[:split]))
    test_acc = accuracy_score(y[split:], model.predict(X[split:]))
    return model, train_acc, test_acc

def backtest_model(stocks, bf, boost_type, model, threshold=0.5):
    signals = 0; correct = 0; returns_sum = 0.0
    for code, rows in stocks.items():
        closes = [r['close'] for r in rows]; highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]; vols = [r['volume'] for r in rows]
        n = len(closes); test_start = LOOKBACK + int((n - LOOKBACK - HORIZON) * 0.7)
        sigs = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost_type)
        for i in range(test_start, n - HORIZON):
            if not sigs[i]: continue
            if closes[i] == 0: continue
            try:
                base = base_features(closes, highs, lows, vols, i)
                consol = consolidation_features(closes, highs, lows, vols, i)
            except: continue
            fv = make_feature_vector(base, consol).reshape(1, -1)
            prob = model.predict_proba(fv)[0]
            if len(prob) > 1 and prob[1] >= threshold:
                signals += 1
                ret = (closes[i+HORIZON] - closes[i]) / closes[i]
                returns_sum += ret
                if ret > 0.005: correct += 1
    wr = correct / signals * 100 if signals else 0
    avg = returns_sum / signals * 100 if signals else 0
    return signals, correct, wr, avg

# ====== Main ======
def main():
    print("Loading stocks...", flush=True)
    stocks = load_stocks()
    print(f"  {len(stocks)} stocks", flush=True)

    print(f"\nTraining with {len(BASE_FEATURE_NAMES)} base + {len(CONSOL_FEATURE_NAMES)} consolidation features = {len(ALL_FEATURE_NAMES)} total", flush=True)
    print(f"{'='*80}", flush=True)

    results = []
    valid = 0; skipped = 0
    for fac in FACTORS_70_PLUS:
        name = fac['name']; boost = fac['boost']
        bf = next((b for b in BASE_FACTORS if b['name'] == name), None)
        if bf is None: continue
        label = f"{name}_{boost}"
        print(f"\n  [{valid+1}/29] {label}...", end='', flush=True)
        X, y = build_dataset(stocks, bf, boost)
        if X is None:
            print(f" SKIP (samples=0)")
            skipped += 1; continue
        model, train_acc, test_acc = train_model(X, y)
        bt_sig, bt_corr, bt_wr, bt_avg = backtest_model(stocks, bf, boost, model)
        results.append({'name':label,'train_acc':round(train_acc,4),'test_acc':round(test_acc,4),'bt_signals':bt_sig,'bt_correct':bt_corr,'bt_win_rate':round(bt_wr,1),'bt_avg_return':round(bt_avg,2),'n_samples':len(X)})
        if bt_sig >= 10 and bt_wr >= 60:
            valid += 1
            save_path = os.path.join(MODEL_DIR, f"best_model_{label}.joblib")
            joblib.dump(model, save_path)
            print(f" SAVED | signals={bt_sig} win={bt_wr}% avg={bt_avg:+.2f}%")
        else:
            skipped += 1
            print(f" LOW | signals={bt_sig} win={bt_wr}% avg={bt_avg:+.2f}%")

    print(f"\n{'='*80}")
    print(f"  Done: {valid} valid, {skipped} skipped", flush=True)

    valid_factors = [r for r in results if r['bt_signals'] >= 10 and r['bt_win_rate'] >= 60]
    valid_factors.sort(key=lambda x: x['bt_win_rate'], reverse=True)
    print(f"\n  有效因子 ({len(valid_factors)} 个):")
    print(f"  {'名称':<26} {'信号':>5} {'胜率':>6} {'均值':>7}")
    for r in valid_factors:
        print(f"  {r['name']:<26} {r['bt_signals']:>5} {r['bt_win_rate']:>5.1f}% {r['bt_avg_return']:>+6.2f}%")

    with open(REPORT_PATH, 'w') as f:
        json.dump({'factors': results, 'data_scope': {'stocks': len(stocks), 'horizon': HORIZON, 'base_features': len(BASE_FEATURE_NAMES), 'consol_features': len(CONSOL_FEATURE_NAMES)}}, f, indent=2, ensure_ascii=False)
    print(f"\n  Report: {REPORT_PATH}")

if __name__ == "__main__":
    main()
