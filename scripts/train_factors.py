#!/usr/bin/env python3
"""
超跌反弹 ML 因子库训练
- 9 基础因子 × 4 增强方式 = 36 组合（去除无效后 ~30 个有效模型）
- XGBoost 训练，滚动时间切分回测
- 最后 30 模型集成投票
- 输出: trained_models/best_model_*.pkl + 报告
"""

import json, os, sys, math, sqlite3, time, pickle
from collections import defaultdict
import numpy as np
import joblib

sys.path.insert(0, '/Users/zhoubo/GP/scripts')
from factors import FACTORS_70_PLUS, BASE_FACTORS, BOOST_TYPES

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
MODEL_DIR = "/Users/zhoubo/GP/scripts/trained_models"
REPORT_PATH = "/Users/zhoubo/GP/scripts/trained_models/pipeline_report.json"
os.makedirs(MODEL_DIR, exist_ok=True)

HORIZON = 20
LOOKBACK = 60
MIN_SAMPLES = 50

# ====== Feature engineering ======

def compute_features(closes, highs, lows, volumes, idx):
    """Return feature dict at day idx."""
    f = {}
    n = len(closes)

    # Returns
    for p in [1, 3, 5, 10, 20]:
        if idx >= p and closes[idx-p] > 0:
            f[f'ret_{p}d'] = (closes[idx] - closes[idx-p]) / closes[idx-p]
        else:
            f[f'ret_{p}d'] = 0.0

    # MA ratios
    for p in [5, 10, 20, 30, 60]:
        if idx >= p-1:
            ma = sum(closes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'ma_{p}_ratio'] = closes[idx] / ma if ma > 0 else 1.0
        else:
            f[f'ma_{p}_ratio'] = 1.0

    # RSI(14)
    if idx >= 14:
        gains = losses = 0.0
        for i in range(idx-13, idx+1):
            d = closes[i] - closes[i-1]
            if d > 0: gains += d
            else: losses -= d
        avg_gain = gains / 14
        avg_loss = losses / 14
        rs = avg_gain / avg_loss if avg_loss > 0 else 999
        f['rsi_14'] = 100 - 100 / (1 + rs)
    else:
        f['rsi_14'] = 50.0

    # Volume ratio
    for p in [5, 20]:
        if idx >= p:
            avg_v = sum(volumes[max(0, idx-p+1):idx+1]) / min(p, idx+1)
            f[f'vol_ratio_{p}'] = volumes[idx] / avg_v if avg_v > 0 else 1.0
        else:
            f[f'vol_ratio_{p}'] = 1.0

    # Volatility (std of daily returns)
    for p in [5, 10, 20]:
        if idx >= p:
            rets = [closes[j] / closes[j-1] - 1 for j in range(idx-p+1, idx+1)]
            f[f'vol_{p}d'] = np.std(rets) if len(rets) > 1 else 0.0
        else:
            f[f'vol_{p}d'] = 0.0

    # Price position in recent range
    for p in [20, 60]:
        if idx >= p:
            lo = min(closes[idx-p:idx+1])
            hi = max(closes[idx-p:idx+1])
            f[f'pos_{p}d'] = (closes[idx] - lo) / (hi - lo) if hi > lo else 0.5
        else:
            f[f'pos_{p}d'] = 0.5

    # ATR ratio
    if idx >= 14:
        trs = [max(highs[j]-lows[j], abs(highs[j]-closes[j-1]), abs(lows[j]-closes[j-1])) for j in range(idx-13, idx+1)]
        atr = sum(trs) / 14
        f['atr_ratio'] = (highs[idx] - lows[idx]) / atr if atr > 0 else 1.0
    else:
        f['atr_ratio'] = 1.0

    # Consecutive down days (last 10)
    down = 0
    for j in range(idx, max(0, idx-10), -1):
        if j >= 1 and closes[j] < closes[j-1]:
            down += 1
        else:
            break
    f['consec_down'] = down

    # Oversold depth (how much below recent high)
    for p in [10, 20, 60]:
        if idx >= p:
            peak = max(closes[idx-p:idx+1])
            f[f'oversold_{p}'] = (closes[idx] - peak) / peak
        else:
            f[f'oversold_{p}'] = 0.0

    return f

FEATURE_NAMES = None  # Will be determined on first call

def feature_names():
    global FEATURE_NAMES
    if FEATURE_NAMES is None:
        FEATURE_NAMES = [
            'ret_1d','ret_3d','ret_5d','ret_10d','ret_20d',
            'ma_5_ratio','ma_10_ratio','ma_20_ratio','ma_30_ratio','ma_60_ratio',
            'rsi_14',
            'vol_ratio_5','vol_ratio_20',
            'vol_5d','vol_10d','vol_20d',
            'pos_20d','pos_60d',
            'atr_ratio','consec_down',
            'oversold_10','oversold_20','oversold_60',
        ]
    return FEATURE_NAMES

def feature_vector(f_dict):
    names = feature_names()
    return np.array([f_dict.get(k, 0.0) for k in names], dtype=np.float64)

# ====== Data loading ======

def load_stocks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code")
    codes = [r["stock_code"] for r in cur.fetchall()]
    result = {}
    for code in codes:
        cur.execute(
            "SELECT trade_date, open, high, low, close, volume FROM kline_data WHERE stock_code=? ORDER BY trade_date",
            (code,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        if len(rows) > LOOKBACK + HORIZON:
            result[code] = rows
    conn.close()
    return result

# ====== Oversold signal detection ======

def oversold_signals(rows, days, drop_pct, consec_down, boost_type):
    """Return list of True/False for each day."""
    closes = [r['close'] for r in rows]
    vols = [r['volume'] for r in rows]
    n = len(closes)
    out = [False] * n
    for i in range(days, n):
        if closes[i-days] <= 0:
            continue
        ret = (closes[i] - closes[i-days]) / closes[i-days]
        if ret >= -drop_pct / 100.0:
            continue
        down_count = 0
        for j in range(i, i-days, -1):
            if j <= 0:
                break
            if closes[j] < closes[j-1]:
                down_count += 1
            else:
                break
        if down_count < consec_down:
            continue
        # Apply boost
        triggered = boost_check(i, closes, vols, boost_type)
        if triggered:
            out[i] = True
    return out

def boost_check(i, closes, vols, boost_type):
    if boost_type == "no_boost":
        return True
    if boost_type == "loose":
        return True
    if boost_type == "rsi_strict":
        if i < 14:
            return False
        gains = losses = 0.0
        for j in range(i-13, i+1):
            d = closes[j] - closes[j-1]
            if d > 0: gains += d
            else: losses -= d
        avg_loss = losses / 14
        if avg_loss == 0:
            return True  # no losses = RSI=100, not oversold
        rs = (gains/14) / avg_loss
        rsi = 100 - 100 / (1 + rs)
        return rsi < 30
    if boost_type == "vol_surge":
        if i < 6:
            return False
        avg_v = sum(vols[i-5:i]) / 5
        if avg_v <= 0:
            return False
        return vols[i] >= 2.0 * avg_v
    return True

# ====== Training ======

def build_dataset(stocks, bf, boost_type):
    """Build (X, y) for one factor+boost combination across all stocks."""
    X, y = [], []
    for code, rows in stocks.items():
        closes = [r['close'] for r in rows]
        highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]
        vols = [r['volume'] for r in rows]
        n = len(closes)

        # Find oversold signal days
        signals = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost_type)

        for i in range(LOOKBACK, n - HORIZON):
            if not signals[i]:
                continue
            try:
                feat = compute_features(closes, highs, lows, vols, i)
            except:
                continue
            if closes[i] == 0:
                continue
            ret = (closes[i+HORIZON] - closes[i]) / closes[i]
            # Label: 1 if future return > 0, -1 if < -2% (noise removed)
            if ret > 0.02:
                label = 1
            elif ret < -0.02:
                label = 0
            else:
                continue
            X.append(feature_vector(feat))
            y.append(label)

    if len(X) < MIN_SAMPLES:
        return None, None
    return np.array(X), np.array(y)

def train_model(X, y):
    """Train XGBoost classifier."""
    from sklearn.model_selection import train_test_split
    import xgboost as xgb
    from sklearn.metrics import accuracy_score

    n = len(X)
    split = int(n * 0.7)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        subsample=0.8,
        use_label_encoder=False,
        eval_metric='logloss',
        verbosity=0,
    )
    model.fit(X_train, y_train)

    train_acc = accuracy_score(y_train, model.predict(X_train))
    test_acc = accuracy_score(y_test, model.predict(X_test))
    return model, train_acc, test_acc

# ====== Backtesting ======

def backtest_model(stocks, bf, boost_type, model, threshold=0.5):
    """Test model on holdout (last 30% of each stock's timeline)."""
    signals = 0
    correct = 0
    returns_sum = 0.0

    for code, rows in stocks.items():
        closes = [r['close'] for r in rows]
        highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]
        vols = [r['volume'] for r in rows]
        n = len(closes)
        test_start = LOOKBACK + int((n - LOOKBACK - HORIZON) * 0.7)

        signals_list = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost_type)

        for i in range(test_start, n - HORIZON):
            if not signals_list[i]:
                continue
            try:
                feat = compute_features(closes, highs, lows, vols, i)
            except:
                continue
            fv = feature_vector(feat).reshape(1, -1)
            prob = model.predict_proba(fv)[0]
            # prob[1] = probability of class 1 (up)
            if len(prob) > 1 and prob[1] >= threshold:
                signals += 1
                ret = (closes[i+HORIZON] - closes[i]) / closes[i]
                returns_sum += ret
                if ret > 0.005:
                    correct += 1

    win_rate = correct / signals * 100 if signals else 0
    avg_ret = returns_sum / signals * 100 if signals else 0
    return signals, correct, win_rate, avg_ret

# ====== Ensemble ======

def ensemble_backtest(stocks, models_info, threshold_ratio=0.5):
    """Run all models, count votes. Signal when votes >= threshold."""
    total_models = len(models_info)
    min_votes = int(total_models * threshold_ratio)

    signals = 0
    correct = 0
    returns_sum = 0.0

    for code, rows in stocks.items():
        closes = [r['close'] for r in rows]
        highs = [r['high'] for r in rows]
        lows = [r['low'] for r in rows]
        vols = [r['volume'] for r in rows]
        n = len(closes)
        test_start = LOOKBACK + int((n - LOOKBACK - HORIZON) * 0.7)

        # For each day, count how many models fire
        for i in range(test_start, n - HORIZON):
            votes = 0
            for bf, boost, model in models_info:
                signals_list = oversold_signals(rows, bf['days'], bf['drop_pct'], bf['consecutive_down'], boost)
                if not signals_list[i]:
                    continue
                try:
                    feat = compute_features(closes, highs, lows, vols, i)
                except:
                    continue
                fv = feature_vector(feat).reshape(1, -1)
                prob = model.predict_proba(fv)[0]
                if len(prob) > 1 and prob[1] >= 0.5:
                    votes += 1

            if votes >= min_votes:
                signals += 1
                ret = (closes[i+HORIZON] - closes[i]) / closes[i]
                returns_sum += ret
                if ret > 0.005:
                    correct += 1

    win_rate = correct / signals * 100 if signals else 0
    avg_ret = returns_sum / signals * 100 if signals else 0
    return signals, correct, win_rate, avg_ret, min_votes

# ====== Main ======

def main():
    print("Loading stocks...")
    stocks = load_stocks()
    print(f"  {len(stocks)} stocks loaded")

    all_factors = []
    valid_count = 0
    invalid_count = 0

    print("\nTraining models...")
    print(f"{'='*80}")

    for fac in FACTORS_70_PLUS:
        name = fac['name']
        boost = fac['boost']

        # Find base factor
        bf = next((b for b in BASE_FACTORS if b['name'] == name), None)
        if bf is None:
            invalid_count += 1
            continue

        label = f"{name}_{boost}"
        print(f"\n  [{valid_count+1}/29] {label}...", end='', flush=True)

        X, y = build_dataset(stocks, bf, boost)
        if X is None:
            print(f" SKIPPED (samples={len(X) if X is not None else 0})")
            invalid_count += 1
            continue

        model, train_acc, test_acc = train_model(X, y)

        # Backtest
        bt_sig, bt_corr, bt_wr, bt_avg = backtest_model(stocks, bf, boost, model)
        model_info = {
            'name': label,
            'days': bf['days'],
            'drop_pct': bf['drop_pct'],
            'consec_down': bf['consecutive_down'],
            'boost': boost,
            'train_acc': round(train_acc, 4),
            'test_acc': round(test_acc, 4),
            'bt_signals': bt_sig,
            'bt_correct': bt_corr,
            'bt_win_rate': round(bt_wr, 1),
            'bt_avg_return_pct': round(bt_avg, 2),
            'n_samples': len(X),
        }
        all_factors.append(model_info)

        if bt_sig >= 10 and bt_wr >= 60:
            valid_count += 1
            save_path = os.path.join(MODEL_DIR, f"best_model_{label}.joblib")
            joblib.dump(model, save_path)
            print(f" SAVED | signals={bt_sig} win={bt_wr}% avg={bt_avg:+.2f}%")
        else:
            invalid_count += 1
            print(f" LOW | signals={bt_sig} win={bt_wr}% avg={bt_avg:+.2f}%")

    print(f"\n{'='*80}")
    print(f"  Training complete: {valid_count} valid models, {invalid_count} skipped")
    print(f"{'='*80}")

    # Print summary table
    valid_factors = [f for f in all_factors if f['bt_signals'] >= 10 and f['bt_win_rate'] >= 60]
    valid_factors.sort(key=lambda x: x['bt_win_rate'], reverse=True)

    print(f"\n  有效因子 ({len(valid_factors)} 个, 胜率≥60%, 信号≥10):")
    print(f"  {'名称':<22} {'信号':>5} {'胜率':>6} {'均值':>7}")
    print(f"  {'─'*22} {'─'*5} {'─'*6} {'─'*7}")
    for f in valid_factors:
        print(f"  {f['name']:<22} {f['bt_signals']:>5} {f['bt_win_rate']:>5.1f}% {f['bt_avg_return_pct']:>+6.2f}%")

    # Ensemble
    if len(valid_factors) >= 3:
        print(f"\n  运行集成回测...")
        models_info = []
        for f in valid_factors:
            bf = next((b for b in BASE_FACTORS if b['name'] == f['name'].rsplit('_', 1)[0]), None)
            if bf is None:
                continue
            save_path = os.path.join(MODEL_DIR, f"best_model_{f['name']}.joblib")
            if os.path.exists(save_path):
                model = joblib.load(save_path)
                models_info.append((bf, f['boost'], model))

        if models_info:
            # Try different thresholds
            for ratio in [0.1, 0.2, 0.3, 0.5, 0.7]:
                sig, corr, wr, avg, votes = ensemble_backtest(stocks, models_info, ratio)
                print(f"  阈值 {votes}/{len(models_info)}: 信号={sig}, 胜率={wr:.1f}%, 均值={avg:+.2f}%")

    # Save report
    report = {
        'total_factors': len(FACTORS_70_PLUS),
        'valid_models': len(valid_factors),
        'skipped': invalid_count,
        'factors': all_factors,
        'data_scope': {'stocks': len(stocks), 'horizon_days': HORIZON},
    }
    with open(REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  Report saved: {REPORT_PATH}")
    print(f"  Models saved: {MODEL_DIR}/")

if __name__ == "__main__":
    main()