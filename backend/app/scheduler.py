"""
APScheduler integration for daily K-line data updates.
SRS §5.4:
  - 每交易日 15:30 增量更新所有自选股日K
  - 每日 16:00 数据完整性检查（近5交易日缺失则补拉）
  - 启动时检查当日数据新鲜度，缺失则立即补拉
"""
import logging
from datetime import datetime, date, time as dtime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def daily_kline_update():
    """Incremental update: fetch latest K-line for all watchlist stocks."""
    from app.db import async_session_maker
    from app.models.watchlist import Watchlist
    from app.services.sync_service import sync_stock_kline
    from sqlalchemy import select

    logger.info("Daily K-line update started")
    async with async_session_maker() as db:
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    if not codes:
        logger.info("No watchlist stocks to update")
        return

    success = 0
    for code in codes:
        try:
            r = await sync_stock_kline(code, days=30)
            if r.get("status") == "ok":
                success += 1
                logger.info(f"Updated {code}: {r['bars']} bars")
            else:
                logger.warning(f"Update {code}: {r.get('message', 'unknown')}")
        except Exception as e:
            logger.error(f"Update {code} failed: {e}")

    logger.info(f"Daily update complete: {success}/{len(codes)} stocks")


async def data_integrity_check():
    """Check last 5 trading days for missing data, backfill if needed."""
    from app.db import async_session_maker
    from app.models.watchlist import Watchlist
    from app.models.kline_data import KlineData
    from app.services.sync_service import sync_stock_kline
    from sqlalchemy import select, func

    logger.info("Data integrity check started")
    async with async_session_maker() as db:
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    for code in codes:
        try:
            async with async_session_maker() as db:
                # Check if we have data for the last 5 calendar days (approx 3-5 trading days)
                from datetime import timedelta
                cutoff = (date.today() - timedelta(days=7)).isoformat()
                count_result = await db.execute(
                    select(func.count(KlineData.id)).where(
                        KlineData.stock_code == code,
                        KlineData.trade_date >= cutoff,
                    )
                )
                recent_count = count_result.scalar() or 0

            if recent_count < 3:
                logger.warning(f"{code}: only {recent_count} recent bars, backfilling...")
                await sync_stock_kline(code, days=30)
        except Exception as e:
            logger.error(f"Integrity check failed for {code}: {e}")

    logger.info("Data integrity check complete")


async def startup_freshness_check():
    """On startup: if it's past 15:30 on a weekday and today's data is missing, sync immediately."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.weekday() >= 5:
        logger.info("Startup freshness check: weekend, skipping")
        return
    if now.time() < dtime(15, 30):
        logger.info("Startup freshness check: before 15:30, skipping")
        return

    from app.db import async_session_maker
    from app.models.watchlist import Watchlist
    from app.models.kline_data import KlineData
    from sqlalchemy import select, func

    async with async_session_maker() as db:
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    if not codes:
        return

    today_str = now.strftime("%Y-%m-%d")
    missing = []
    async with async_session_maker() as db:
        for code in codes:
            count_result = await db.execute(
                select(func.count(KlineData.id)).where(
                    KlineData.stock_code == code,
                    KlineData.trade_date == today_str,
                )
            )
            if (count_result.scalar() or 0) == 0:
                missing.append(code)

    if missing:
        logger.warning(f"Startup freshness check: {len(missing)} stocks missing today's data ({today_str}), syncing now...")
        from app.services.sync_service import sync_stock_kline
        for code in missing:
            try:
                r = await sync_stock_kline(code, days=30)
                logger.info(f"Startup sync {code}: {r.get('status')} ({r.get('bars', 0)} bars)")
            except Exception as e:
                logger.error(f"Startup sync {code} failed: {e}")
    else:
        logger.info(f"Startup freshness check: all {len(codes)} stocks have today's data")


async def news_refresh_job():
    """Refresh industry news (investment-news RSS + AI digest)."""
    try:
        from app.services.news_service import refresh_all_sectors
        await refresh_all_sectors()
        logger.info("News refresh complete")
    except Exception as e:
        logger.error(f"News refresh failed: {e}")


async def info_cache_warmup():
    """Pre-warm info cache for watchlist stocks (concepts, lockup, etc.)."""
    from app.db import async_session_maker
    from app.models.watchlist import Watchlist
    from app.services import info_service
    from sqlalchemy import select

    async with async_session_maker() as db:
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    for code in codes[:20]:  # limit to 20 to avoid overloading
        try:
            await info_service.get_overview(code)
        except Exception as e:
            logger.warning(f"Cache warmup failed for {code}: {e}")

    logger.info(f"Info cache warmup done for {min(len(codes), 20)} stocks")


async def prediction_eval_job():
    """Evaluate due predictions and update model accuracy (D2)."""
    from app.services.prediction_eval import evaluate_due_predictions
    try:
        result = await evaluate_due_predictions()
        logger.info(f"Prediction eval job done: {result}")
    except Exception as e:
        logger.error(f"Prediction eval job failed: {e}")


def start_scheduler():
    """Start the scheduler with daily update jobs."""
    # Daily K-line update at 15:30 (Mon-Fri)
    scheduler.add_job(
        daily_kline_update,
        trigger=CronTrigger(hour=15, minute=30, day_of_week="mon-fri"),
        id="daily_kline_update",
        name="Daily K-line incremental update",
        replace_existing=True,
        misfire_grace_time=7200,
        coalesce=True,
        max_instances=1,
    )

    # Data integrity check at 16:00 (Mon-Fri)
    scheduler.add_job(
        data_integrity_check,
        trigger=CronTrigger(hour=16, minute=0, day_of_week="mon-fri"),
        id="data_integrity_check",
        name="Daily data integrity check",
        replace_existing=True,
        misfire_grace_time=7200,
        coalesce=True,
        max_instances=1,
    )

    # D2: 到期预测评估（16:05，紧接数据完整性检查之后）
    scheduler.add_job(
        prediction_eval_job,
        trigger=CronTrigger(hour=16, minute=5, day_of_week="mon-fri"),
        id="prediction_eval_job",
        name="Daily prediction evaluation",
        replace_existing=True,
        misfire_grace_time=7200,
        coalesce=True,
        max_instances=1,
    )

    # Secondary safety net: check data freshness every 30 min from 15:30 to 22:00
    scheduler.add_job(
        _periodic_freshness_check,
        trigger=CronTrigger(hour="15-21", minute="0,30", day_of_week="mon-fri"),
        id="periodic_freshness_check",
        name="Periodic data freshness check",
        replace_existing=True,
        misfire_grace_time=600,
        coalesce=True,
        max_instances=1,
    )

    # News refresh: 已改用 launchd 定时任务（com.gp.investment-news，每4小时），此处停用
    # scheduler.add_job(
    #     news_refresh_job,
    #     trigger=CronTrigger(hour="8,12,20", minute=0),
    #     id="news_refresh",
    #     name="Industry news refresh (RSS + AI)",
    #     replace_existing=True,
    #     misfire_grace_time=3600,
    #     coalesce=True,
    #     max_instances=1,
    # )

    # Daily database backup: 21:00 every day, keep last 7
    from scripts.backup_db import backup_job
    scheduler.add_job(
        backup_job,
        trigger=CronTrigger(hour=21, minute=0),
        id="daily_db_backup",
        name="Daily database backup",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )

    # Info cache warmup: 09:00 weekdays (pre-market)
    scheduler.add_job(
        info_cache_warmup,
        trigger=CronTrigger(hour=9, minute=0, day_of_week="mon-fri"),
        id="info_cache_warmup",
        name="Pre-market info cache warmup",
        replace_existing=True,
        misfire_grace_time=1800,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Scheduler started: kline@15:30, integrity@16:00, freshness@30min, backup@21:00, warmup@9:00")


async def _periodic_freshness_check():
    """Every 30 min (15:00-22:00 weekdays): verify today's data exists, backfill if missing."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.time() < dtime(15, 15):
        return  # market not closed yet

    from app.db import async_session_maker
    from app.models.watchlist import Watchlist
    from app.models.kline_data import KlineData
    from app.services.sync_service import sync_stock_kline
    from sqlalchemy import select, func

    today_str = now.strftime("%Y-%m-%d")
    async with async_session_maker() as db:
        result = await db.execute(select(Watchlist.stock_code))
        codes = [row[0] for row in result.all()]

    for code in codes:
        try:
            async with async_session_maker() as db:
                count_result = await db.execute(
                    select(func.count(KlineData.id)).where(
                        KlineData.stock_code == code,
                        KlineData.trade_date == today_str,
                    )
                )
                if (count_result.scalar() or 0) == 0:
                    logger.warning(f"Freshness check: {code} missing {today_str}, backfilling...")
                    await sync_stock_kline(code, days=30)
        except Exception as e:
            logger.error(f"Freshness check failed for {code}: {e}")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")