"""Price alerts router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_db
from app.models.alert import Alert
from app.schemas import AlertCreate, AlertRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(stock_code: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Alert).order_by(Alert.created_at.desc())
    if stock_code:
        q = q.where(Alert.stock_code == stock_code)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=AlertRead, status_code=201)
async def create_alert(data: AlertCreate, db: AsyncSession = Depends(get_db)):
    alert = Alert(
        stock_code=data.stock_code,
        stock_name=data.stock_name,
        alert_type=data.alert_type,
        target_price=data.target_price,
        direction=data.direction,
        pct_threshold=data.pct_threshold,
        volume_ratio=data.volume_ratio,
        volume_days=data.volume_days,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()
