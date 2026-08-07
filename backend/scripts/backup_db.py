"""Daily database backup: copy stock.db to data/backups/, keep last 7."""
import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock.db"
BACKUP_DIR = DB_PATH.parent / "backups"
KEEP = 7


def run_backup() -> str:
    """Copy stock.db to backups/stock_YYYYmmdd_HHMMSS.db, prune old ones. Returns backup path."""
    BACKUP_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"stock_{ts}.db"
    shutil.copy2(DB_PATH, dest)

    backups = sorted(BACKUP_DIR.glob("stock_*.db"))
    for old in backups[:-KEEP]:
        old.unlink()
        logger.info(f"Pruned old backup: {old.name}")

    logger.info(f"Database backed up: {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
    return str(dest)


async def backup_job():
    """Async wrapper for APScheduler."""
    try:
        run_backup()
    except Exception as e:
        logger.error(f"Database backup failed: {e}")


if __name__ == "__main__":
    print(run_backup())
