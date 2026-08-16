#!/usr/bin/env python3
"""超跌因子集成回测（模型已训练，仅跑集成投票验证，修复 train_factors.py 的 StopIteration 后可用）。

用法: python run_ensemble_backtest.py
"""
import os, sys, json, joblib
LIMIT = int(os.environ.get("LIMIT", "0"))
sys.path.insert(0, '/Users/zhoubo/GP/scripts')
from factors import FACTORS_70_PLUS, BASE_FACTORS
from train_factors import load_stocks, ensemble_backtest, MODEL_DIR, REPORT_PATH

def main():
    print("Loading stocks...")
    stocks = load_stocks()
    if LIMIT:
        stocks = dict(list(stocks.items())[:LIMIT])
    print(f"  {len(stocks)} stocks")

    models_info = []
    for f in FACTORS_70_PLUS:
        bf = next((b for b in BASE_FACTORS if b['name'] == f['name']), None)
        if bf is None:
            continue
        save_path = os.path.join(MODEL_DIR, f"best_model_{f['name']}_{f['boost']}.joblib")
        if os.path.exists(save_path):
            models_info.append((bf, f['boost'], joblib.load(save_path)))
    print(f"  {len(models_info)} models loaded")

    print("\n运行集成回测（不同投票阈值）...")
    results = []
    for ratio in [0.1, 0.2, 0.3, 0.5, 0.7]:
        sig, corr, wr, avg, votes = ensemble_backtest(stocks, models_info, ratio)
        results.append({"threshold": ratio, "signals": sig, "correct": corr,
                        "win_rate": wr, "avg_pct": avg, "votes": votes})
        print(f"  阈值≥{ratio:.0%}: 信号 {sig} 只, 胜率 {wr:.1f}%, 均值 {avg:+.2f}%")

    report = {"ensemble": results, "models": len(models_info),
              "data_scope": {"stocks": len(stocks)}}
    with open(REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n  报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    main()
