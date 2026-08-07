"""Prediction persistence (D1) — 预测结果落库，供 D2 到期评估与准确率统计。

设计：每次 predict 调用时，把每个模型的 trend/confidence + 当时收盘价落一条记录。
落库是 fire-and-forget，任何异常都吞掉，绝不影响主预测流程。
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker
from app.models.kline_data import KlineData
from app.models.prediction_record import PredictionRecord

logger = logging.getLogger(__name__)


async def _latest_close(stock_code: str, db: AsyncSession) -> float:
    row = await db.execute(
        select(KlineData.close)
        .where(KlineData.stock_code == stock_code)
        .order_by(desc(KlineData.trade_date))
        .limit(1)
    )
    val = row.scalar()
    return float(val) if val is not None else 0.0


async def record_prediction(stock_code: str, days: int, models: dict) -> int:
    """Persist one record per model output. Returns number of records written.

    Never raises — logs and returns 0 on any failure.
    """
    try:
        predict_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        written = 0
        async with async_session_maker() as db:
            price = await _latest_close(stock_code, db)
            for name, result in (models or {}).items():
                if not isinstance(result, dict) or result.get("status") == "error":
                    continue
                trend = result.get("trend") or result.get("final_trend") or "unknown"
                conf = result.get("confidence")
                if conf is None:
                    conf = result.get("weighted_confidence", 0)
                try:
                    conf = float(conf)
                except (TypeError, ValueError):
                    conf = 0.0
                rec = PredictionRecord(
                    stock_code=stock_code,
                    predict_date=predict_date,
                    model_name=name,
                    horizon_days=days,
                    trend=str(trend),
                    confidence=conf,
                    price_at_predict=price,
                )
                db.add(rec)
                written += 1
            if written:
                await db.commit()
        return written
    except Exception as e:
        logger.warning(f"record_prediction failed for {stock_code}: {e}")
        return 0
