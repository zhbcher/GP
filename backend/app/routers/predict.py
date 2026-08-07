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
async def predict_stock(code: str, days: int = 5, llm: bool = False, db: AsyncSession = Depends(get_db)):
    if days < 1 or days > 20:
        raise HTTPException(400, "days must be between 1 and 20")

    import asyncio
    tech = TechnicalPredictor()
    stat = StatisticalPredictor()
    mc = MonteCarloPredictor()
    pat = PatternRecognizer()
    xgb = XGBoostPredictor()
    dl = DeepLearningPredictor()

    tech_result, stat_result, mc_result, pat_result, xgb_result, dl_result = await asyncio.gather(
        tech.predict(code, days),
        stat.predict(code, days),
        mc.predict(code, days),
        pat.predict(code, days),
        xgb.predict(code, days),
        dl.predict(code, days),
        return_exceptions=True
    )

    models = {}
    for name, result in [("technical", tech_result), ("statistical", stat_result),
                         ("monte_carlo", mc_result), ("patterns", pat_result),
                         ("ml", xgb_result), ("deep_learning", dl_result)]:
        if isinstance(result, Exception):
            models[name] = {"error": str(result), "status": "error"}
        else:
            models[name] = result

    ensemble = EnsemblePredictor()
    try:
        ensemble_result = await ensemble.ensemble(models, days)
    except Exception as e:
        ensemble_result = {"error": str(e), "status": "error"}

    # LLM 分析报告（可选，默认关闭避免拖慢主接口）
    llm_result = None
    if llm:
        try:
            from app.services.predictors.llm_analyzer import analyze_with_llm
            from app.services.prediction_store import _latest_close
            # K线摘要：最近 5 日涨跌
            from sqlalchemy import select as _select
            from app.models.kline_data import KlineData as _K
            _rows = (await db.execute(
                _select(_K).where(_K.stock_code == code)
                .order_by(_K.trade_date.desc()).limit(5)
            )).scalars().all()
            _rows = list(reversed(_rows))
            if len(_rows) >= 2:
                chg = (_rows[-1].close / _rows[0].close - 1) * 100
                kline_summary = (f"最近{len(_rows)}个交易日从 {_rows[0].close} 走到 {_rows[-1].close}，"
                                 f"累计{'+' if chg>=0 else ''}{chg:.2f}%。")
            else:
                kline_summary = "数据不足"
            stock_name = code
            from app.models.watchlist import Watchlist as _W
            _wl = await db.scalar(_select(_W).where(_W.stock_code == code))
            if _wl:
                stock_name = _wl.stock_name
            llm_result = await analyze_with_llm(code, stock_name, kline_summary, models, ensemble_result)
        except Exception as e:
            logger.warning(f"llm analyze skipped: {e}")
            llm_result = {"status": "error", "error": str(e)[:200]}

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
        "ensemble": ensemble_result,
        **({"llm": llm_result} if llm_result else {}),
    }
