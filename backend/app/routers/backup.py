"""Backup / restore router."""
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from app.config import get_settings

router = APIRouter(prefix="/api/backup", tags=["backup"])
settings = get_settings()

DB_PATH = Path(settings.database_url.replace("sqlite+aiosqlite:///", ""))


@router.get("")
async def download_backup():
    if not DB_PATH.exists():
        raise HTTPException(404, "Database file not found")
    return FileResponse(
        path=str(DB_PATH),
        filename="stock_watchlist_backup.db",
        media_type="application/octet-stream",
    )


@router.post("")
async def restore_backup(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".db"):
        raise HTTPException(400, "Please upload a .db file")
    # Save uploaded file
    backup_path = DB_PATH.with_suffix(".db.restore")
    with open(backup_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    # Replace current DB
    old_path = DB_PATH.with_suffix(".db.old")
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, old_path)
    shutil.move(backup_path, DB_PATH)
    return {"status": "ok", "message": "Database restored. Restart the backend to apply."}
