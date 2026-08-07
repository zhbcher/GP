from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Index
from datetime import datetime
from app.db import Base
from app.models.mixins import TimestampMixin


class Drawing(Base, TimestampMixin):
    __tablename__ = "drawings"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, index=True)
    period: str = Column(String(10), nullable=False, default="daily")
    type: str = Column(String(30), nullable=False)
    points: str = Column(Text, nullable=False)  # JSON string
    style: str = Column(Text, default="{}")     # JSON string
    text_content: str | None = Column(Text, nullable=True)
    visible: bool = Column(Boolean, default=True)
    idempotency_key: str | None = Column(String(64), nullable=True, unique=True)

    __table_args__ = (
        Index("idx_drawing_code_period", "stock_code", "period"),
    )
