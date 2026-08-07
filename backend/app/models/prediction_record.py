"""Prediction record model — 预测回测落库（D1）。

每次调用 predict 时，每个模型的输出（趋势/置信度/预测时价格）落一条记录。
到期后由 scheduler job 对比实际收盘价，算出对/错，统计各模型准确率。
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, Index
from app.db import Base


class PredictionRecord(Base):
    __tablename__ = "prediction_records"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, index=True)
    predict_date: str = Column(String(10), nullable=False)   # 'YYYY-MM-DD'
    model_name: str = Column(String(40), nullable=False)     # technical/statistical/...
    horizon_days: int = Column(Integer, nullable=False, default=5)
    trend: str = Column(String(20), nullable=False)          # bullish/bearish/neutral/unknown
    confidence: float = Column(Float, default=0)
    price_at_predict: float = Column(Float, default=0)       # 预测时最新收盘价

    # 到期评估后回填
    evaluated: bool = Column(Boolean, default=False)
    eval_date: str = Column(String(10), nullable=True)
    price_at_eval: float = Column(Float, nullable=True)
    actual_trend: str = Column(String(20), nullable=True)    # up/down/flat (按阈值)
    is_correct: bool = Column(Boolean, nullable=True)

    __table_args__ = (
        Index("idx_pred_code_date_model", "stock_code", "predict_date", "model_name"),
    )
