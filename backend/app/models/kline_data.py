from sqlalchemy import Column, Integer, String, Date, Float, BigInteger, Index
from app.db import Base


class KlineData(Base):
    __tablename__ = "kline_data"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, index=True)
    trade_date: str = Column(String(10), nullable=False)  # '2024-09-30'
    open: float = Column(Float, nullable=False)
    high: float = Column(Float, nullable=False)
    low: float = Column(Float, nullable=False)
    close: float = Column(Float, nullable=False)
    volume: int = Column(BigInteger, nullable=False)
    amount: float = Column(Float, default=0)

    __table_args__ = (
        Index("idx_kline_code_date", "stock_code", "trade_date", unique=True),
    )
