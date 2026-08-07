from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base
from app.models.mixins import TimestampMixin


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(50), nullable=False, unique=True)
    sort_order: int = Column(Integer, default=0)

    watchlists = relationship("Watchlist", back_populates="group", cascade="all, delete-orphan")
