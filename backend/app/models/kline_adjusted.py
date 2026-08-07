from sqlalchemy import Column, Integer, String, Float, BigInteger, Index
from app.db import Base


class KlineAdjusted(Base):
    """Authoritative adjusted K-line cache fetched from akshare (eastmoney).

    adj_type: 'qfq' (forward) or 'hfq' (backward). The main kline_data table
    stores unadjusted prices only; this table caches adjusted series on demand.
    """

    __tablename__ = "kline_adjusted"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, index=True)
    trade_date: str = Column(String(10), nullable=False)
    adj_type: str = Column(String(4), nullable=False)  # 'qfq' | 'hfq'
    open: float = Column(Float, nullable=False)
    high: float = Column(Float, nullable=False)
    low: float = Column(Float, nullable=False)
    close: float = Column(Float, nullable=False)
    volume: int = Column(BigInteger, nullable=False)
    amount: float = Column(Float, default=0)

    __table_args__ = (
        Index("idx_kadj_code_date_type", "stock_code", "trade_date", "adj_type", unique=True),
    )
