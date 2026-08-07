"""Price alert model."""
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_code: Mapped[str] = mapped_column(String(20), index=True)
    stock_name: Mapped[str] = mapped_column(String(50), default="")
    alert_type: Mapped[str] = mapped_column(String(20), default="price")  # price / change_pct / volume
    # price alert params
    target_price: Mapped[float] = mapped_column(Float, default=0)
    direction: Mapped[str] = mapped_column(String(10), default="above")  # above / below
    # change_pct alert params
    pct_threshold: Mapped[float] = mapped_column(Float, default=0)  # e.g. 5.0 means 5%
    # volume alert params
    volume_ratio: Mapped[float] = mapped_column(Float, default=0)  # e.g. 2.0 means 2x average
    volume_days: Mapped[int] = mapped_column(Integer, default=5)  # N-day average
    # status
    triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
