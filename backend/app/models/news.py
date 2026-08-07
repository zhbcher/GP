from sqlalchemy import Column, Integer, String, Text, DateTime, Index, UniqueConstraint
from datetime import datetime
from app.db import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    sector: str = Column(String(50), nullable=False, index=True)
    title: str = Column(String(500), nullable=False)
    title_zh: str = Column(String(500), default="")
    link: str = Column(String(1000), default="")
    date: str = Column(String(100), default="")
    published_at: str = Column(String(20), default="")  # YYYY-MM-DD (Beijing time)
    summary: str = Column(Text, default="")
    content: str = Column(Text, default="")  # full article text (original language)
    content_zh: str = Column(Text, default="")  # translated Chinese content
    source: str = Column(String(200), default="")
    fetched_at: datetime = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_news_sector_fetched", "sector", "fetched_at"),
        Index("idx_news_published", "published_at"),
        Index("idx_news_sector_date", "sector", "published_at"),
    )


class NewsDigest(Base):
    __tablename__ = "news_digests"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    sector: str = Column(String(50), nullable=False)
    date: str = Column(String(20), nullable=False)  # YYYY-MM-DD
    points: str = Column(Text, default="")  # JSON array of key point strings
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("sector", "date", name="uq_digest_sector_date"),
    )
