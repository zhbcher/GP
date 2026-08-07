"""Stock prediction router."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.services.predictors import (
    TechnicalPredictor, StatisticalPredictor, MonteCarloPredictor,
    PatternRecognizer, XGBoostPredictor, EnsemblePredictor, DeepLearningPredictor
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stock", tags=["predict"])

@router.get("/{code}/predict")
async def predict_stock(code: str, days: int = 5, db: AsyncSession = Depends(get_db)):
    if days < 1 or days > 20:
        raise HTTPException(400, "days must be between 1 and 20")

    import asyncio
    tech = TechnicalPredictor()
    stat = StatisticalPredictor()
    mc = MonteCarloPredictor()
    pat = PatternRecognizer()
    xgb = XGBoostPredictor()

    tech_result, stat_result, mc_result, pat_result, xgb_result = await asyncio.gather(
        tech.predict(code, days),
        stat.predict(code, days),
        mc.predict(code, days),
        pat.predict(code, days),
        xgb.predict(code, days),
        return_exceptions=True
    )

    models = {}
    for name, result in [("technical", tech_result), ("statistical", stat_result),
                         ("monte_carlo", mc_result), ("patterns", pat_result),
                         ("ml", xgb_result)]:
        if isinstance(result, Exception):
            models[name] = {"error": str(result), "status": "error"}
        else:
            models[name] = result

    ensemble = EnsemblePredictor()
    try:
        ensemble_result = await ensemble.ensemble(models)
    except Exception as e:
        ensemble_result = {"error": str(e), "status": "error"}

    # D1: 落库预测记录（fire-and-forget，失败不阻塞主流程）
    try:
        from app.services.prediction_store import record_prediction
        all_for_store = dict(models)
        all_for_store["ensemble"] = ensemble_result
        asyncio.create_task(record_prediction(code, days, all_for_store))
    except Exception as e:
        logger.warning(f"prediction persist skipped: {e}")

    return {
        "code": code,
        "current_price": 0,
        "models": models,
        "ensemble": ensemble_result
    }
