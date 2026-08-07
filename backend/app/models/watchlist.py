from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base
from app.models.mixins import TimestampMixin


class Watchlist(Base, TimestampMixin):
    __tablename__ = "watchlist"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    stock_code: str = Column(String(20), nullable=False, unique=True)
    stock_name: str = Column(String(50), nullable=False)
    group_id: int | None = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    note: str = Column(Text, default="")
    sort_order: int = Column(Integer, default=0)

    group = relationship("Group", back_populates="watchlists")

    __table_args__ = (
        Index("idx_watchlist_group", "group_id"),
    )
