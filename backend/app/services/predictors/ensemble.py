"""G方案: 融合器 — 多模型加权投票。

权重来源优先级：
1. 回测准确率表 docs/backtest-result.json（horizon 匹配时），accuracy 越高权重越大
2. 实时预测记录表 prediction_records 的历史准确率（样本足够时叠加修正）
3. 都没有 → 等权

投票规则：
- 每个模型输出归一化为 direction ∈ {-1, 0, +1}（空/多/平）+ confidence ∈ [0,1]
- 加权得分 score = Σ(w_i * direction_i * confidence_i)，权重按模型归一化
- final_trend: score > +TREND_THRESHOLD → up；< -TREND_THRESHOLD → down；否则 neutral
- 置信度 = |score| 上限 1
- target_price: 取 statistical / ml / monte_carlo 的中位目标价（若可得）
"""
import json
import logging
import os
from statistics import median

logger = logging.getLogger(__name__)

# docs/backtest-result.json 的相对路径（相对 backend/ 运行时 cwd 或项目根）
BACKTEST_RESULT_CANDIDATES = [
    os.path.expanduser("~/GP/docs/backtest-result.json"),
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "backtest-result.json"),
]

TREND_THRESHOLD = 0.15          # 加权得分阈值
NEUTRAL_PROB_BAND = 0.02        # monte_carlo/ml 的 up_probability 落在 0.5±该区间 → 视为平

# predict API 的 models key → 回测 JSON 的模型名
BACKTEST_NAME_ALIAS = {"ml": "xgboost"}


def _accuracy_to_weight(acc: float) -> float:
    """回测准确率 → 融合权重。

    - acc < 50%: 比随机还差，压到 0.1 保留极小发言权（回测本身有噪声，不硬剔除）
    - acc >= 50%: 0.3 起步，每超 1% 加 0.10
    """
    a = acc / 100.0 if acc > 1.5 else acc
    if a < 0.50:
        return 0.10
    return 0.30 + (a - 0.50) * 10.0


def _load_backtest_weights(horizon: int) -> dict:
    """从回测结果读取各模型准确率 → 权重。找不到返回 {}。"""
    for path in BACKTEST_RESULT_CANDIDATES:
        path = os.path.abspath(path)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
            block = data.get(str(horizon)) or data.get(horizon) or {}
            if not block:
                continue
            weights = {}
            for model, stat in block.items():
                acc = stat.get("accuracy")
                if acc is None:
                    continue
                weights[model] = _accuracy_to_weight(float(acc))
            if weights:
                logger.info(f"ensemble weights from backtest(h={horizon}): {weights}")
                return weights
        except Exception as e:
            logger.warning(f"load backtest weights failed ({path}): {e}")
    return {}


def _model_vote(name: str, result: dict) -> tuple:
    """把单个模型输出归一化成 (direction, confidence)。direction∈{-1,0,1}。"""
    if not isinstance(result, dict) or result.get("status") == "error":
        return (0, 0.0)

    def prob_to_dir(p):
        if p is None:
            return 0
        p = float(p)
        if p > 0.5 + NEUTRAL_PROB_BAND:
            return 1
        if p < 0.5 - NEUTRAL_PROB_BAND:
            return -1
        return 0

    if name == "technical":
        trend = result.get("trend")
        conf = float(result.get("confidence", 0.5))
        d = 1 if trend == "up" else -1 if trend == "down" else 0
        return (d, conf)

    if name == "statistical":
        trend = result.get("trend")
        d = 1 if trend == "up" else -1 if trend == "down" else 0
        # 用 r2 作为置信度（越高越可信），缺失给中等
        r2 = result.get("r2")
        conf = max(0.3, min(1.0, float(r2))) if r2 is not None else 0.5
        return (d, conf)

    if name in ("monte_carlo", "ml"):
        p = result.get("up_probability")
        d = prob_to_dir(p)
        conf = abs(float(p) - 0.5) * 2 if p is not None else 0.0
        return (d, min(1.0, max(0.0, conf)))

    if name == "patterns":
        patterns = result.get("patterns") or []
        up = sum(1 for x in patterns if x.get("direction") == "up")
        down = sum(1 for x in patterns if x.get("direction") == "down")
        if up == 0 and down == 0:
            return (0, 0.0)
        d = 1 if up > down else -1 if down > up else 0
        total = up + down
        conf = abs(up - down) / total if total else 0.0
        return (d, conf)

    if name == "deep_learning":
        # LSTM 门禁：回测/验证集方向准确率 < 52% 则不参与融合
        if name == "deep_learning":
            acc = float(result.get("direction_accuracy") or 0)
            if acc < 0.52:
                return (0, 0.0)
        # LSTM 输出 forecast 序列，用首尾方向
        forecast = result.get("forecast") or []
        cur = result.get("current_price")
        if len(forecast) >= 1 and cur:
            last = forecast[-1].get("price")
            if last:
                d = 1 if last > cur else -1 if last < cur else 0
                band = abs(float(last) - float(cur)) / float(cur)
                return (d, min(1.0, band * 10))
        return (0, 0.0)

    if name == "llm":
        sug = (result.get("suggestion") or "").lower()
        if "买" in sug or "看多" in sug or "buy" in sug:
            return (1, 0.5)
        if "卖" in sug or "看空" in sug or "sell" in sug:
            return (-1, 0.5)
        return (0, 0.0)

    return (0, 0.0)


class EnsemblePredictor:
    async def ensemble(self, models: dict, days: int = 5) -> dict:
        models = models or {}

        # 1. 权重
        weights = _load_backtest_weights(days)

        # 2. 投票
        votes = {}
        weighted_score = 0.0
        weight_sum = 0.0
        for name, result in models.items():
            direction, confidence = _model_vote(name, result)
            w = weights.get(BACKTEST_NAME_ALIAS.get(name, name), 1.0)
            if direction == 0 and confidence == 0.0 and name not in weights and BACKTEST_NAME_ALIAS.get(name) not in weights:
                # 无有效信号且无先验权重的模型跳过
                votes[name] = {"direction": 0, "confidence": 0.0, "weight": 0.0}
                continue
            votes[name] = {
                "direction": direction,
                "confidence": round(confidence, 3),
                "weight": round(w, 3),
                "backtest_weighted": name in weights or BACKTEST_NAME_ALIAS.get(name) in weights,
            }
            weighted_score += w * direction * confidence
            weight_sum += w

        if weight_sum <= 0:
            return {
                "final_trend": "neutral",
                "weighted_confidence": 0,
                "model_weights": {},
                "score": 0,
                "status": "no_signal",
            }

        score = weighted_score / weight_sum  # 归一化到 [-1, 1]

        if score > TREND_THRESHOLD:
            final_trend = "up"
        elif score < -TREND_THRESHOLD:
            final_trend = "down"
        else:
            final_trend = "neutral"

        weighted_confidence = round(min(1.0, abs(score)), 3)

        # 3. 归一化权重（展示用）
        norm_weights = {
            name: round(v["weight"] / weight_sum, 3)
            for name, v in votes.items()
        }

        # 4. 目标价（取可用预测的中位数）
        targets = []
        stat = models.get("statistical") or {}
        if stat.get("forecast"):
            try:
                targets.append(float(stat["forecast"][-1]["price"]))
            except Exception:
                pass
        mc = models.get("monte_carlo") or {}
        if mc.get("median"):
            targets.append(float(mc["median"]))
        dl = models.get("deep_learning") or {}
        if dl.get("forecast"):
            try:
                targets.append(float(dl["forecast"][-1]["price"]))
            except Exception:
                pass
        target_price = round(median(targets), 2) if targets else None

        return {
            "final_trend": final_trend,
            "weighted_confidence": weighted_confidence,
            "score": round(score, 4),
            "model_weights": norm_weights,
            "votes": votes,
            "target_price": target_price,
            "status": "ok",
        }
