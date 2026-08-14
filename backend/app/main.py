import logging
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, time

# All data sources are domestic China services; bypass system proxy
os.environ.setdefault("no_proxy", "*")
os.environ.setdefault("NO_PROXY", "*")
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from app.config import get_settings
from app.db import engine, Base, async_session_maker
from app.auth import auth_middleware_handler
from app.routers import health, search, stock, watchlist, drawings, annotations, ws, sync, alerts, positions, backup, auth, info, market, news, journal, chips, screen, data_io, predict, predict_acc, report
from app.services.realtime_service import connection_manager, get_realtime_quotes
from app.data_sources.manager import manager, DataSourceError
from app.data_sources.mootdx_source import MootdxSource
from app.data_sources.akshare_source import AkshareSource
from app.data_sources.easyquotation_source import EasyquotationSource
from app.data_sources.tencent_source import TencentSource
from app.scheduler import start_scheduler, stop_scheduler, startup_freshness_check
from app.models.news import NewsItem  # noqa: F401 — ensure table creation
from app.models.kline_adjusted import KlineAdjusted  # noqa: F401 — ensure table creation
from app.models.prediction_record import PredictionRecord  # noqa: F401 — ensure table creation (D1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


def _is_trading_hours() -> bool:
    """Check if current time is within A-share trading hours."""
    now = datetime.now()
    weekday = now.weekday()
    if weekday >= 5:
        return False
    t = now.time()
    return time(9, 15) <= t <= time(11, 30) or time(13, 0) <= t <= time(15, 5)


async def _realtime_poll_loop():
    """Poll realtime quotes and broadcast via WebSocket."""
    from app.models.watchlist import Watchlist

    while True:
        try:
            if not _is_trading_hours():
                await asyncio.sleep(60)
                continue

            async with async_session_maker() as db:
                result = await db.execute(select(Watchlist.stock_code))
                codes = [row[0] for row in result.all()]

            if not codes:
                await asyncio.sleep(settings.realtime_poll_interval)
                continue

            quotes = await get_realtime_quotes(codes)
            if quotes:
                await connection_manager.broadcast({
                    "type": "quote_update",
                    "data": quotes,
                    "timestamp": datetime.now().isoformat(),
                })
                # BE-002: check price alerts
                await _check_alerts(quotes, db)

            await asyncio.sleep(settings.realtime_poll_interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Realtime poll error: {e}")
            await asyncio.sleep(settings.realtime_poll_interval)


async def _get_avg_volume(db, stock_code: str, days: int) -> float:
    """Get average daily volume over the past N trading days from kline data."""
    from app.models.kline_data import KlineData
    from sqlalchemy import desc
    result = await db.execute(
        select(KlineData.volume)
        .where(KlineData.stock_code == stock_code)
        .order_by(desc(KlineData.trade_date))
        .limit(days)
    )
    volumes = [row[0] for row in result.all() if row[0]]
    if not volumes:
        return 0
    return sum(volumes) / len(volumes)


async def _check_alerts(quotes: dict, db):
    """Check all active alerts (price / change_pct / volume) and trigger if conditions met."""
    from app.models.alert import Alert
    from app.services.notify import notify_alert_triggered

    result = await db.execute(select(Alert).where(Alert.triggered == False))
    pending_alerts = result.scalars().all()
    for alert in pending_alerts:
        q = quotes.get(alert.stock_code)
        if not q:
            continue
        price = q.get("price", 0)
        if price <= 0:
            continue

        triggered = False
        trigger_value = ""
        extra_info = ""

        if alert.alert_type == "price":
            # Price alert: current price crosses target
            triggered = (
                (alert.direction == "above" and price >= alert.target_price) or
                (alert.direction == "below" and price <= alert.target_price)
            )
            trigger_value = f"{alert.direction == 'above' and '涨到' or '跌到'} {alert.target_price:.2f}"

        elif alert.alert_type == "change_pct":
            # Change percentage alert: abs(change_pct) >= threshold
            change_pct = q.get("change_pct", 0)
            if change_pct:
                abs_pct = abs(change_pct)
                if alert.direction == "above" and change_pct >= alert.pct_threshold:
                    triggered = True
                elif alert.direction == "below" and change_pct <= -alert.pct_threshold:
                    triggered = True
                elif alert.direction == "above" and abs_pct >= alert.pct_threshold:
                    # fallback: if direction is above but no sign check, use abs
                    triggered = True
                trigger_value = f"涨跌幅 {change_pct:+.2f}% 超 {'涨' if alert.direction == 'above' else '跌'} {alert.pct_threshold:.1f}%"
                extra_info = f"涨跌幅: {change_pct:+.2f}%"

        elif alert.alert_type == "volume":
            # Volume alert: current cumulative volume >= N-day avg * ratio
            current_volume = q.get("volume", 0)
            if current_volume and alert.volume_days > 0 and alert.volume_ratio > 0:
                avg_volume = await _get_avg_volume(db, alert.stock_code, alert.volume_days)
                if avg_volume and avg_volume > 0:
                    threshold_vol = avg_volume * alert.volume_ratio
                    if current_volume >= threshold_vol:
                        triggered = True
                        trigger_value = f"成交量 {current_volume} >= {alert.volume_days}日均量 {avg_volume:.0f} × {alert.volume_ratio}"
                        extra_info = f"当日量: {current_volume}, {alert.volume_days}日均量: {avg_volume:.0f}, 倍数: {current_volume / avg_volume:.2f}"

        if triggered:
            alert.triggered = True
            alert.triggered_at = datetime.now()
            await connection_manager.broadcast({
                "type": "alert_triggered",
                "data": {
                    "id": alert.id,
                    "stock_code": alert.stock_code,
                    "stock_name": alert.stock_name,
                    "alert_type": alert.alert_type,
                    "target_price": alert.target_price,
                    "direction": alert.direction,
                    "current_price": price,
                    "trigger_value": trigger_value,
                },
                "timestamp": datetime.now().isoformat(),
            })
            # Push Feishu notification (silently fails if no webhook configured)
            await notify_alert_triggered(
                stock_name=alert.stock_name,
                stock_code=alert.stock_code,
                alert_type=alert.alert_type,
                trigger_value=trigger_value,
                current_price=price,
                direction=alert.direction,
                extra_info=extra_info,
            )
    await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

    # Lightweight migration: add new columns if missing
    async with engine.begin() as conn:
        for col, typedef in [
            ("title_zh", "VARCHAR(500) DEFAULT ''"),
            ("published_at", "VARCHAR(20) DEFAULT ''"),
            ("content", "TEXT DEFAULT ''"),
            ("content_zh", "TEXT DEFAULT ''"),
        ]:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE news_items ADD COLUMN {col} {typedef}")
                logger.info(f"Migration: added news_items.{col}")
            except Exception:
                pass  # column already exists
        # news_digests: add sector column
        try:
            await conn.exec_driver_sql("ALTER TABLE news_digests ADD COLUMN sector VARCHAR(50) DEFAULT ''")
            logger.info("Migration: added news_digests.sector")
        except Exception:
            pass
        # alerts: add new columns for MV-003 (alert_type, pct_threshold, volume_ratio, volume_days)
        for col, typedef in [
            ("alert_type", "VARCHAR(20) DEFAULT 'price'"),
            ("pct_threshold", "FLOAT DEFAULT 0"),
            ("volume_ratio", "FLOAT DEFAULT 0"),
            ("volume_days", "INTEGER DEFAULT 5"),
        ]:
            try:
                await conn.exec_driver_sql(f"ALTER TABLE alerts ADD COLUMN {col} {typedef}")
                logger.info(f"Migration: added alerts.{col}")
            except Exception:
                pass

    # Register data sources (priority: mootdx > akshare > easyquotation > tencent)
    try:
        manager.register(MootdxSource())
    except Exception as e:
        logger.warning(f"mootdx registration failed: {e}")
    manager.register(AkshareSource())
    manager.register(EasyquotationSource())
    manager.register(TencentSource())
    logger.info("Data sources registered")

    # Startup sync disabled (causes DB lock + OOM on low-memory devices)
    # Re-enable manually by calling: POST /api/sync/all
    logger.info("Startup sync skipped (manual mode)")

    # Start realtime polling
    poll_task = asyncio.create_task(_realtime_poll_loop())
    logger.info("Realtime polling started")

    # Start APScheduler for daily updates
    start_scheduler()

    # Startup freshness check: fire-and-forget with timeout to avoid blocking startup
    async def _freshness_with_timeout():
        try:
            await asyncio.wait_for(startup_freshness_check(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Startup freshness check timed out (mootdx unreachable), skipping")
        except Exception as e:
            logger.error(f"Startup freshness check failed: {e}")
    asyncio.create_task(_freshness_with_timeout())

    # Load persisted news from DB into memory cache
    from app.services.news_service_v2 import load_news_on_startup
    await load_news_on_startup()

    yield

    poll_task.cancel()
    stop_scheduler()


async def startup_fast():
    """Fast startup without freshness check (avoids mootdx timeout)."""
    pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Global auth middleware ----

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    return await auth_middleware_handler(request, call_next)


app.include_router(auth.router)
app.include_router(health.router)
app.include_router(search.router)
app.include_router(stock.router)
app.include_router(watchlist.router)
app.include_router(drawings.router)
app.include_router(annotations.router)
app.include_router(ws.router)
app.include_router(alerts.router)
app.include_router(positions.router)
app.include_router(backup.router)
app.include_router(sync.router)
app.include_router(info.router)
app.include_router(market.router)
app.include_router(news.router)
app.include_router(journal.router)
app.include_router(chips.router)
app.include_router(screen.router)
app.include_router(data_io.router)
app.include_router(predict.router)
app.include_router(predict_acc.router)
app.include_router(report.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
