from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from datetime import datetime
import uuid
from app.db import Base
from app.models.mixins import TimestampMixin


def _gen_uuid():
    return str(uuid.uuid4())


class Annotation(Base, TimestampMixin):
    __tablename__ = "annotations"

    id: str = Column(String(36), primary_key=True, default=_gen_uuid)
    stock_code: str = Column(String(20), nullable=False, index=True)
    trade_date: str = Column(String(10), nullable=False)
    type: str = Column(String(20), nullable=False, default="watch")
    content: str = Column(Text, nullable=False)
    position: str = Column(String(10), default="above")
    idempotency_key: str | None = Column(String(64), nullable=True, unique=True)

    __table_args__ = (
        Index("idx_annotation_code_date", "stock_code", "trade_date"),
    )
