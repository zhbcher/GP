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
