"""Prediction evaluation (D2) — 到期预测对比实际走势，统计各模型准确率。

评估逻辑：
- 到期判定：predict_date 之后已有 >= horizon_days 根日K
- 取第 horizon_days 根交易日收盘价为 price_at_eval
- actual_trend: 涨幅 > +0.5% → up；< -0.5% → down；否则 flat
- is_correct: bullish↔up / bearish↔down / neutral↔flat；trend=unknown 的记录
  不计入准确率（is_correct 保持 NULL）
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_maker
from app.models.kline_data import KlineData
from app.models.prediction_record import PredictionRecord

logger = logging.getLogger(__name__)

TREND_THRESHOLD = 0.005  # ±0.5% 以内算 flat

MODEL_TREND_MAP = {"bullish": "up", "bearish": "down", "neutral": "flat",
                   "up": "up", "down": "down"}


async def _eval_one(db: AsyncSession, rec: PredictionRecord) -> bool:
    """Evaluate a single due record. Returns True if marked evaluated."""
    rows = await db.execute(
        select(KlineData.trade_date, KlineData.close)
        .where(
            KlineData.stock_code == rec.stock_code,
            KlineData.trade_date > rec.predict_date,
        )
        .order_by(KlineData.trade_date)
        .limit(rec.horizon_days)
    )
    seq = rows.all()
    if len(seq) < rec.horizon_days:
        return False  # 还没到足够的交易日

    eval_date, price_at_eval = seq[-1][0], float(seq[-1][1])
    if rec.price_at_predict and rec.price_at_predict > 0:
        chg = price_at_eval / rec.price_at_predict - 1
    else:
        chg = 0.0

    if chg > TREND_THRESHOLD:
        actual = "up"
    elif chg < -TREND_THRESHOLD:
        actual = "down"
    else:
        actual = "flat"

    rec.evaluated = True
    rec.eval_date = eval_date
    rec.price_at_eval = price_at_eval
    rec.actual_trend = actual
    expected = MODEL_TREND_MAP.get(rec.trend)
    rec.is_correct = (expected == actual) if expected is not None else None
    return True


async def evaluate_due_predictions() -> dict:
    """Scan all unevaluated records and evaluate those that are due."""
    evaluated = skipped = 0
    async with async_session_maker() as db:
        result = await db.execute(
            select(PredictionRecord).where(PredictionRecord.evaluated == False)  # noqa: E712
        )
        records = list(result.scalars().all())
        for rec in records:
            try:
                if await _eval_one(db, rec):
                    evaluated += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.warning(f"eval failed for record {rec.id}: {e}")
                skipped += 1
        if evaluated:
            await db.commit()
    logger.info(f"prediction eval: evaluated={evaluated} not_due={skipped}")
    return {"evaluated": evaluated, "not_due": skipped}


async def get_accuracy_stats() -> list[dict]:
    """Per-model accuracy over evaluated records (is_correct not null)."""
    async with async_session_maker() as db:
        rows = await db.execute(
            select(
                PredictionRecord.model_name,
                func.count(PredictionRecord.id),
                func.sum(func.cast(PredictionRecord.is_correct, Integer)),
            )
            .where(
                PredictionRecord.evaluated == True,  # noqa: E712
                PredictionRecord.is_correct != None,  # noqa: E711
            )
            .group_by(PredictionRecord.model_name)
        )
        stats = []
        for name, total, correct in rows.all():
            correct = correct or 0
            stats.append({
                "model": name,
                "samples": int(total),
                "correct": int(correct),
                "accuracy": round(correct / total * 100, 1) if total else 0.0,
            })
        return sorted(stats, key=lambda x: -x["accuracy"])
