from sqlalchemy import Column, Integer, String, Date, Float, Index
from app.db import Base


class AdjustFactor(Base):
    __tablename__ = "adjust_factor"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, index=True)
    trade_date: str = Column(String(10), nullable=False)
    factor: float = Column(Float, nullable=False)

    __table_args__ = (
        Index("idx_adjust_code_date", "stock_code", "trade_date", unique=True),
    )
