"""Daily database backup: VACUUM INTO compressed snapshot, layered retention.

- 使用 VACUUM INTO 生成压缩一致性快照（比 copy 小，消除删除后的空洞）
- 保留策略：日备份保留 7 份 + 每月首份额外保留 6 个月
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock.db"
BACKUP_DIR = DB_PATH.parent / "backups"
KEEP_DAILY = 7       # 日备份保留份数
KEEP_MONTHLY = 6     # 每月首份额外保留月数


def run_backup() -> str:
    """VACUUM INTO 压缩备份。返回备份路径。"""
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"stock_{ts}.db"

    # VACUUM INTO：一致性快照 + 压缩碎片（比文件 copy 小）
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute(f"VACUUM INTO '{dest}'")
    conn.close()

    _prune()
    logger.info(f"Database backed up: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB, 压缩快照)")
    return str(dest)


def _prune():
    """分层清理：最近 KEEP_DAILY 份保留；每月首份保留 KEEP_MONTHLY 个月。"""
    backups = sorted(BACKUP_DIR.glob("stock_*.db"))
    for old in backups[:-KEEP_DAILY]:
        # 每月首份（该月份最早一份）额外保留 KEEP_MONTHLY 个月
        try:
            dt = datetime.strptime(old.name, "stock_%Y%m%d_%H%M%S.db")
        except ValueError:
            old.unlink()
            continue
        month_key = dt.strftime("%Y%m")
        same_month_earlier = [b for b in backups if b.name.startswith(f"stock_{month_key}") and b < old]
        is_month_first = not same_month_earlier
        if is_month_first:
            age_months = (datetime.now().year - dt.year) * 12 + (datetime.now().month - dt.month)
            if age_months < KEEP_MONTHLY:
                continue  # 保留
        old.unlink()
        logger.info(f"Pruned backup: {old.name}")


async def backup_job():
    """Async wrapper for APScheduler."""
    try:
        run_backup()
    except Exception as e:
        logger.error(f"Database backup failed: {e}")


if __name__ == "__main__":
    print(run_backup())
