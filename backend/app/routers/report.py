"""Daily after-market report routes (F1)."""
import logging
from fastapi import APIRouter

from app.services.daily_report import send_daily_report, generate_daily_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])


@router.post("/daily")
async def trigger_daily_report():
    """手动触发盘后日报（生成 + 飞书推送）。"""
    return await send_daily_report()


@router.get("/daily/preview")
async def preview_daily_report():
    """仅生成日报文本（不推送），用于预览/调试。"""
    text = await generate_daily_report()
    return {"text": text}
