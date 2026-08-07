from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ---- Group ----

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    sort_order: Optional[int] = None


class GroupRead(BaseModel):
    id: int
    name: str
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Watchlist ----

class WatchlistCreate(BaseModel):
    stock_code: str = Field(..., min_length=1, max_length=20)
    stock_name: str = Field(..., min_length=1, max_length=50)
    group_id: Optional[int] = None
    note: str = ""


class WatchlistUpdate(BaseModel):
    note: Optional[str] = None
    group_id: Optional[int] = None
    sort_order: Optional[int] = None


class WatchlistRead(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    group_id: Optional[int]
    note: str
    sort_order: int
    created_at: datetime

    class Config:
        from_attributes = True


class WatchlistWithRealtime(WatchlistRead):
    realtime: Optional[dict] = None


# ---- Kline ----

class KlineDataRead(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float = 0


class KlineResponse(BaseModel):
    code: str
    name: str
    period: str
    adjust: str
    data: list[KlineDataRead]
    count: int


# ---- Drawing ----

class DrawingCreate(BaseModel):
    stock_code: str
    period: str = "daily"
    type: str
    points: list[dict]  # [{"timestamp": ..., "value": ...}]
    style: dict = {}
    text_content: Optional[str] = None
    idempotency_key: Optional[str] = None


class DrawingUpdate(BaseModel):
    style: Optional[dict] = None
    points: Optional[list[dict]] = None
    visible: Optional[bool] = None
    text_content: Optional[str] = None


class DrawingRead(BaseModel):
    id: int
    stock_code: str
    period: str
    type: str
    points: list[dict]
    style: dict
    text_content: Optional[str]
    visible: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Annotation ----

class AnnotationCreate(BaseModel):
    stock_code: str
    trade_date: str
    type: str = "watch"
    content: str = Field(..., min_length=1, max_length=500)
    position: str = "above"
    idempotency_key: Optional[str] = None


class AnnotationUpdate(BaseModel):
    type: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1, max_length=500)
    position: Optional[str] = None


class AnnotationRead(BaseModel):
    id: str
    stock_code: str
    trade_date: str
    type: str
    content: str
    position: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnnotationDisplayUpdate(BaseModel):
    stock_code: str
    type: Optional[str] = None  # None = all types
    visible: bool = True


# ---- Search ----

class StockSearchResult(BaseModel):
    code: str
    name: str
    pinyin: str = ""


# ---- Alert ----

class AlertCreate(BaseModel):
    stock_code: str
    stock_name: str = ""
    alert_type: str = "price"  # price / change_pct / volume
    # price alert params
    target_price: float = 0
    direction: str = "above"  # above / below
    # change_pct alert params
    pct_threshold: float = 0  # e.g. 5.0 means 5%
    # volume alert params
    volume_ratio: float = 0  # e.g. 2.0 means 2x average
    volume_days: int = 5  # N-day average


class AlertRead(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    alert_type: str
    target_price: float
    direction: str
    pct_threshold: float
    volume_ratio: float
    volume_days: int
    triggered: bool
    triggered_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Position ----

class PositionCreate(BaseModel):
    stock_code: str
    stock_name: str = ""
    cost_price: float
    quantity: int
    buy_date: str = ""
    note: str = ""


class PositionUpdate(BaseModel):
    cost_price: Optional[float] = None
    quantity: Optional[int] = None
    buy_date: Optional[str] = None
    note: Optional[str] = None


class PositionRead(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    cost_price: float
    quantity: int
    buy_date: str
    note: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Health ----

class HealthResponse(BaseModel):
    status: str
    version: str
    data_sources: dict
