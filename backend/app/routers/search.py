from fastapi import APIRouter, Query
from app.db import async_session_maker
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/search")
async def search(q: str = Query(..., min_length=1), limit: int = Query(20, le=100)):
    """Search stocks by code or name from database."""
    try:
        async with async_session_maker() as db:
            keyword = q.strip()
            
            # Search in watchlist first (has names)
            stmt = text("""
                SELECT stock_code, stock_name 
                FROM watchlist 
                WHERE stock_code LIKE :pattern1 
                   OR stock_code LIKE :pattern2
                   OR stock_name LIKE :pattern3
                ORDER BY stock_code
                LIMIT :limit
            """)
            
            rows = await db.execute(stmt, {
                "pattern1": f"%{keyword}%",
                "pattern2": f"{keyword}%",
                "pattern3": f"%{keyword}%",
                "limit": limit
            })
            
            results = []
            seen = set()
            for code, name in rows.fetchall():
                if code not in seen:
                    results.append({
                        "code": code,
                        "name": name,
                        "pinyin": ""
                    })
                    seen.add(code)
            
            # If no results from watchlist, search kline_data
            if not results:
                stmt2 = text("""
                    SELECT DISTINCT stock_code 
                    FROM kline_data 
                    WHERE stock_code NOT LIKE 'sh000%' 
                      AND stock_code NOT LIKE 'sz399%'
                      AND (stock_code LIKE :pattern1 OR stock_code LIKE :pattern2)
                    ORDER BY stock_code
                    LIMIT :limit
                """)
                
                rows2 = await db.execute(stmt2, {
                    "pattern1": f"%{keyword}%",
                    "pattern2": f"{keyword}%",
                    "limit": limit
                })
                
                for (code,) in rows2.fetchall():
                    results.append({
                        "code": code,
                        "name": code.upper(),
                        "pinyin": ""
                    })
            
            return results[:limit]
            
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []
