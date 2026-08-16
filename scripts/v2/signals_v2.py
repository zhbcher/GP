#!/usr/bin/env python3
"""
GP 选股方案 v2 — 每日信号输出 + 市场状态 + 建议仓位

1. 市场状态：全市场等权 60 日累计收益 → 牛(>+5%) / 震荡 / 熊(<-5%)
2. 建议仓位：牛 50%（转防御） / 震荡 100% / 熊 30%
3. 选股：综合得分（4因子反向合成）→ 得分前 10~20% + 过滤（价格/流动性）
4. 输出 JSON：代码/收盘价/得分/各因子值/市场状态/建议仓位

用法:
  python signals_v2.py                # 输出今日信号
  python signals_v2.py --top 0.15     # Top 15%
  python signals_v2.py --save         # 保存到 signals_v2_YYYYMMDD.json
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from factors_v2 import compute_factors_for_stock
from scorer_v2 import EFFECTIVE_FACTORS, composite_score

DB_PATH = "/Users/zhoubo/GP/data/stock.db"
LOOKBACK = 400  # 加载最近 N 个交易日（因子窗口最大 60 日，400 足够）
MIN_PRICE = 3.0
MIN_AMT = 3e7


def market_regime_and_position(panel: pd.DataFrame) -> tuple[str, float, float]:
    """全市场等权 60 日累计收益 → (状态, 建议仓位, 60日收益)。"""
    mkt = panel.groupby(level="date")["close"].mean()
    mkt = mkt.sort_index()
    ret60 = mkt.iloc[-1] / mkt.iloc[-61] - 1.0 if len(mkt) > 61 else 0.0
    if ret60 > 0.05:
        return "牛", 0.5, ret60
    if ret60 < -0.05:
        return "熊", 0.3, ret60
    return "震荡", 1.0, ret60


def push_to_feishu(title: str, body: str, user_open_id: str = "ou_3cc9159f8a1ced8fef38f172777b0d6e") -> bool:
    """推送消息到飞书（复用 hermes 应用 bot；不影响网关的事件监听）。"""
    import os
    import subprocess
    env = dict(os.environ)
    env["HERMES_HOME"] = "/Users/zhoubo/.lark-cli/hermes"
    text = f"{title}\n{body}"
    try:
        r = subprocess.run(
            ["lark-cli", "im", "+messages-send", "--as", "bot",
             "--user-id", user_open_id, "--text", text],
            capture_output=True, text=True, timeout=60, env=env)
        ok = r.returncode == 0 and '"ok": true' in r.stdout
        if not ok:
            print(f"  [push] 失败: {r.stderr[:200]}")
        return ok
    except Exception as e:
        print(f"  [push] 异常: {e}")
        return False


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=float, default=0.15, help="得分前 top 比例")
    ap.add_argument("--save", action="store_true", help="保存 JSON")
    ap.add_argument("--push", action="store_true", help="推送摘要到飞书")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    codes = pd.read_sql("SELECT DISTINCT stock_code FROM kline_data ORDER BY stock_code", conn)["stock_code"].tolist()
    # 防御：剔除错误前缀（深市代码不应有 sh 前缀）
    codes = [c for c in codes if not (c.startswith("sh") and c[2:5] in ("000", "001", "002", "003"))]

    print(f"[1/3] 加载 {len(codes)} 只股票最近 {LOOKBACK} 日...")
    parts = []
    for i, code in enumerate(codes):
        df = pd.read_sql(
            "SELECT trade_date, open, high, low, close, volume, amount FROM kline_data "
            "WHERE stock_code=? ORDER BY trade_date DESC LIMIT ?", conn, params=(code, LOOKBACK))
        if len(df) < 120:
            continue
        df = df.sort_values("trade_date").reset_index(drop=True)
        f = compute_factors_for_stock(df.set_index("trade_date"))
        f = f.reset_index()
        f["stock_code"] = code
        f["close"] = df["close"].values
        f["amt_60"] = df["amount"].rolling(60).mean().values
        f = f.dropna(subset=list(EFFECTIVE_FACTORS.keys()))
        if len(f) == 0:
            continue
        parts.append(f.set_index(["trade_date", "stock_code"]))
        if (i + 1) % 2000 == 0:
            print(f"  [{i + 1}/{len(codes)}] {time.time() - t0:.0f}s")
    conn.close()
    panel = pd.concat(parts)
    panel.index = panel.index.set_names(["date", "stock_code"])
    print(f"  面板 {panel.shape}, {time.time() - t0:.0f}s")

    print("[2/3] 市场状态 + 综合得分...")
    regime, pos, ret60 = market_regime_and_position(panel)
    print(f"  市场状态: {regime}（全市场60日收益 {ret60:+.1%}）, 建议仓位 {pos:.0%}")

    score = composite_score(panel)
    last_date = panel.index.get_level_values("date").max()
    today = panel.xs(last_date, level="date")
    sc = score.xs(last_date, level="date")
    tmp = pd.DataFrame({
        "score": sc, "close": today["close"], "amt": today["amt_60"],
        **{k: today[k] for k in EFFECTIVE_FACTORS},
    }).dropna()
    tmp = tmp[(tmp["close"] >= MIN_PRICE) & (tmp["amt"] >= MIN_AMT)]
    tmp = tmp.sort_values("score", ascending=False)

    n_top = max(int(len(tmp) * args.top), 10)
    top = tmp.head(n_top)
    print(f"[3/3] 选股结果（{last_date}, 得分前 {args.top:.0%}, 过滤后 {len(tmp)} 只候选 → 选 {n_top} 只）")

    rows = []
    for code, r in top.iterrows():
        rows.append({
            "stock_code": code,
            "close": round(float(r["close"]), 2),
            "score": round(float(r["score"]), 3),
            "factors": {k: (round(float(r[k]), 4) if pd.notna(r[k]) else None) for k in EFFECTIVE_FACTORS},
        })

    print(f"\n{'=' * 70}")
    print(f"  {last_date} 选股信号（Top {args.top:.0%}, 共 {len(rows)} 只）")
    print(f"  市场: {regime} | 建议仓位: {pos:.0%}")
    print(f"{'=' * 70}")
    for r in rows[:30]:
        fv = r["factors"]
        print(f"  {r['stock_code']}  价 {r['close']:>7.2f}  分 {r['score']:>6.2f}  "
              f"振幅{fv['V2_amp']:.3f} 强度{fv['M1_rps20']:+.2f} 均线{fv['M3_ma_align']:.0f} 换手{fv['S5_vol_turn']:.2f}")
    if len(rows) > 30:
        print(f"  ... 共 {len(rows)} 只")

    if args.save:
        out_path = Path(__file__).parent / f"signals_v2_{datetime.now().strftime('%Y%m%d')}.json"
        payload = {
            "date": last_date,
            "market_regime": regime,
            "market_ret_60d": round(ret60, 4),
            "suggested_position": pos,
            "top_ratio": args.top,
            "n_candidates": len(tmp),
            "signals": rows,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"\n  已保存: {out_path}")

    if args.push:
        print("\n[push] 推送摘要到飞书...")
        lines = [
            f"📊 选股信号 {last_date}",
            f"市场: {regime}（60日 {ret60:+.1%}）| 建议仓位: {pos:.0%}",
            f"Top {args.top:.0%} 共 {len(rows)} 只，前 10 只：",
        ]
        for r in rows[:10]:
            fv = r["factors"]
            lines.append(
                f"  {r['stock_code']} ¥{r['close']:.2f} 分{r['score']:.2f} "
                f"(振幅{fv['V2_amp']:.3f}/强度{fv['M1_rps20']:+.2f}/换手{fv['S5_vol_turn']:.2f})")
        ok = push_to_feishu("🔔 DeepSeek Harness 选股日报", "\n".join(lines))
        print(f"  [push] {'成功' if ok else '失败'}")
    print(f"\n  总耗时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
