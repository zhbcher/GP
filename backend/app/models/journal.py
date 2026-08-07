from sqlalchemy import Column, Integer, String, Text, Date, DateTime, UniqueConstraint
from datetime import datetime
from app.db import Base
from app.models.mixins import TimestampMixin


class Journal(Base, TimestampMixin):
    __tablename__ = "journals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, unique=True)
    operations = Column(Text, nullable=False, default="")
    market_obs = Column(Text, nullable=False, default="")
    plan = Column(Text, nullable=False, default="")
    mood = Column(String(20), nullable=False, default="neutral")

    __table_args__ = (
        UniqueConstraint("trade_date", name="uq_journal_trade_date"),
    )
