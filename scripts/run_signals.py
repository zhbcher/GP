#!/usr/bin/env python3
"""
全市场超跌反弹信号生成器 - 双版本并行
原版：红色圆点 ●
震荡增强版：红色三角形 ▲
输出两套结果
"""
import sys, os, json, glob, time, sqlite3
import numpy as np
import xgboost as xgb
import joblib
from datetime import datetime
from factors import BASE_FACTORS, BOOST_TYPES

sys.path.append('/Users/zhoubo/GP/scripts')

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MODEL_DIRS = {
    "base": "/Users/zhoubo/GP/scripts/trained_models",
    "consolidation": "/Users/zhoubo/GP/scripts/trained_models_consolidation",
}
HORIZON = 20
THRESHOLDS = [11, 14, 17, 19]

# ====== 特征函数（两套） ======
# 原版特征
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

def base_feature_vector(f_dict):
    return np.array([f_dict.get(k, 0.0) for k in BASE_FEATURE_NAMES], dtype=np.float64)

# 震荡增强版特征
def consol_features(closes, highs, lows, volumes, idx):
    f = base_features(closes, highs, lows, volumes, idx)
    for w in [10, 20, 30, 45, 60]:
        if idx >= w:
            hi = max(highs[idx-w+1:idx+1]); lo = min(lows[idx-w+1:idx+1])
            f[f'consol_range_{w}d'] = (hi - lo) / lo if lo > 0 else 0
        else: f[f'consol_range_{w}d'] = 1.0
    if idx >= 40:
        cur_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(idx-9, idx+1)]
        prev_ret = [closes[j]/closes[j-1]-1 if closes[j-1]>0 else 0 for j in range(idx-29, idx-10)]
        f['consol_vol_shrink'] = np.std(cur_ret) / np.std(prev_ret) if np.std(prev_ret) > 0 else 1.0
    else: f['consol_vol_shrink'] = 1.0
    for w in [20, 60, 120]:
        if idx >= w:
            hi = max(closes[idx-w+1:idx+1]); lo = min(closes[idx-w+1:idx+1])
            f[f'consol_pos_{w}d'] = (closes[idx]-lo)/(hi-lo) if hi > lo else 0.5
        else: f[f'consol_pos_{w}d'] = 0.5
    if idx >= 20:
        recent_v = sum(volumes[idx-4:idx+1])/5; prev_v = sum(volumes[idx-19:idx-5])/15
        f['consol_vol_shrink_ratio'] = recent_v / prev_v if prev_v > 0 else 1.0
    else: f['consol_vol_shrink_ratio'] = 1.0
    consec = 0
    for w in [10, 20, 30]:
        if idx >= w:
            hi = max(highs[idx-w+1:idx+1]); lo = min(lows[idx-w+1:idx+1])
            width = (hi-lo)/lo if lo > 0 else 1
            if width < 0.08: consec = w; break
    f['consol_consec_days'] = consec
    if idx >= 20:
        hi = max(highs[idx-19:idx]); lo = min(lows[idx-19:idx])
        f['consol_breakout_up'] = 1.0 if closes[idx] > hi else 0.0
        f['consol_breakout_down'] = 1.0 if closes[idx] < lo else 0.0
    else: f['consol_breakout_up'] = 0.0; f['consol_breakout_down'] = 0.0
    if idx >= 19:
        ma5 = sum(closes[idx-4:idx+1])/5; ma20 = sum(closes[idx-19:idx+1])/20
        f['consol_above_ma20'] = 1.0 if closes[idx] > ma20 else 0.0
        f['consol_ma5_above_ma20'] = 1.0 if ma5 > ma20 else 0.0
    else: f['consol_above_ma20'] = 0.0; f['consol_ma5_above_ma20'] = 0.0
    if idx >= 59:
        ma60 = sum(closes[idx-59:idx+1])/60; ma20 = sum(closes[idx-19:idx+1])/20
        f['consol_ma20_above_ma60'] = 1.0 if ma20 > ma60 else 0.0
    else: f['consol_ma20_above_ma60'] = 0.0
    return f

CONSOL_FEATURE_NAMES = [
    'consol_range_10d','consol_range_20d','consol_range_30d','consol_range_45d','consol_range_60d',
    'consol_vol_shrink',
    'consol_pos_20d','consol_pos_60d','consol_pos_120d',
    'consol_vol_shrink_ratio',
    'consol_consec_days',
    'consol_breakout_up','consol_breakout_down',
    'consol_above_ma20','consol_ma5_above_ma20','consol_ma20_above_ma60',
]

def consol_feature_vector(f_dict):
    vec = [f_dict.get(k, 0.0) for k in BASE_FEATURE_NAMES]
    vec += [f_dict.get(k, 0.0) for k in CONSOL_FEATURE_NAMES]
    return np.array(vec, dtype=np.float64)

# ====== 超跌信号 ======
def oversold_signals(rows, days, drop_pct, consec_down, boost_type):
    closes = [r['close'] for r in rows]; vols = [r['volume'] for r in rows]
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

# ====== 加载模型 ======
def load_models(model_dir):
    model_files = sorted(glob.glob(os.path.join(model_dir, "best_model_*.joblib")))
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
    return models_info

# ====== 主逻辑 ======
def main():
    print(f"加载模型...", flush=True)
    base_models = load_models(MODEL_DIRS["base"])
    consol_models = load_models(MODEL_DIRS["consolidation"])
    print(f"  原版: {len(base_models)} 个, 震荡版: {len(consol_models)} 个", flush=True)

    print(f"加载股票数据...", flush=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code")
    codes = [r[0] for r in cur.fetchall()]

    results = {"base": {t: [] for t in THRESHOLDS}, "consolidation": {t: [] for t in THRESHOLDS}}
    t0 = time.time()

    for ci, code in enumerate(codes):
        if ci % 500 == 0: print(f"  [{ci}/{len(codes)}] {time.time()-t0:.0f}s", flush=True)
        cur.execute("SELECT trade_date, open, high, low, close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date", (code,))
        rows = [{'trade_date':r[0],'open':r[1],'high':r[2],'low':r[3],'close':r[4],'volume':r[5]} for r in cur.fetchall()]
        if len(rows) < 80: continue
        closes = [r['close'] for r in rows]; highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]; vols = [r['volume'] for r in rows]
        i = len(closes) - 1

        # 计算特征
        try:
            base_f = base_features(closes, highs, lows, vols, i)
            consol_f = consol_features(closes, highs, lows, vols, i)
        except: continue
        base_fv = base_feature_vector(base_f).reshape(1, -1)
        consol_fv = consol_feature_vector(consol_f).reshape(1, -1)

        # 原版投票
        base_votes = 0
        for bf, boost, model, _ in base_models:
            sigs = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost)
            if not sigs[-1]: continue
            prob = model.predict_proba(base_fv)[0]
            if len(prob) > 1 and prob[1] >= 0.5: base_votes += 1

        # 震荡版投票
        consol_votes = 0
        for bf, boost, model, _ in consol_models:
            sigs = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost)
            if not sigs[-1]: continue
            prob = model.predict_proba(consol_fv)[0]
            if len(prob) > 1 and prob[1] >= 0.5: consol_votes += 1

        for t in THRESHOLDS:
            if base_votes >= t:
                results["base"][t].append((code, closes[i], base_votes))
            if consol_votes >= t:
                results["consolidation"][t].append((code, closes[i], consol_votes))

    conn.close()

    # 输出
    today = datetime.now().strftime('%Y-%m-%d')
    print(f"\n{'='*70}", flush=True)
    print(f"  {today} 超跌反弹信号", flush=True)
    print(f"{'='*70}", flush=True)

    for version_name, label_mark, label_str in [("base", "●", "原版"), ("consolidation", "▲", "震荡增强")]:
        print(f"\n  {label_str} {label_mark} (共 {len(results[version_name][THRESHOLDS[0]])} 只)", flush=True)
        for t in THRESHOLDS:
            n = len(results[version_name][t])
            label = {11:"保守",14:"稳健",17:"积极",19:"激进"}[t]
            print(f"    {label}({t}/26): {n} 只", flush=True)
            if n > 0:
                for code, price, votes in results[version_name][t][:10]:
                    print(f"      {label_mark} {code} ¥{price:.2f} 投票:{votes}/26", flush=True)
                if n > 10: print(f"      ... 还有 {n-10} 只", flush=True)

    # 保存
    output = {
        'date': today,
        'total_stocks': len(codes),
        'base': {str(t): [{'code':c,'price':p,'votes':v} for c,p,v in s] for t,s in results['base'].items()},
        'consolidation': {str(t): [{'code':c,'price':p,'votes':v} for c,p,v in s] for t,s in results['consolidation'].items()},
    }
    out_path = f"/Users/zhoubo/GP/scripts/trained_models/signals_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  已保存: {out_path}", flush=True)

if __name__ == "__main__":
    main()
