"""Prediction accuracy routes (D2)."""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/predict", tags=["predict-accuracy"])


@router.get("/accuracy")
async def predict_accuracy():
    """各模型预测准确率（仅统计已到期评估且 trend 可判定的记录）。"""
    from app.services.prediction_eval import get_accuracy_stats
    stats = await get_accuracy_stats()
    return {"models": stats, "count": len(stats)}


@router.post("/evaluate")
async def predict_evaluate():
    """手动触发到期预测评估（用于测试/补跑）。"""
    from app.services.prediction_eval import evaluate_due_predictions
    return await evaluate_due_predictions()


@router.get("/backtest")
async def predict_backtest():
    """walk-forward 历史回测准确率（docs/backtest-result.json）。"""
    import json, os
    path = os.path.expanduser("~/GP/docs/backtest-result.json")
    if not os.path.exists(path):
        return {"horizons": {}, "report": None}
    with open(path) as f:
        data = json.load(f)
    report_path = os.path.expanduser("~/GP/docs/backtest-report.md")
    report = None
    if os.path.exists(report_path):
        with open(report_path) as f:
            report = f.read()
    return {"horizons": data, "report": report}
