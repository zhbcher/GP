"""选股 v2 信号接口：读取当日信号 JSON 返回给前端。"""
import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/api/screen-v2", tags=["screen-v2"])

SIGNALS_DIR = Path("/Users/zhoubo/GP/scripts/v2")


@router.get("/latest")
async def get_latest_signals():
    """返回最新一期选股信号（读 signals_v2_YYYYMMDD.json）。"""
    files = sorted(SIGNALS_DIR.glob("signals_v2_*.json"), reverse=True)
    if not files:
        return {"ok": False, "message": "暂无信号（先运行 signals_v2.py）"}
    data = json.loads(files[0].read_text(encoding="utf-8"))
    return {"ok": True, "file": files[0].name, **data}
