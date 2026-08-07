"""Daily after-market report (F1) — 盘后日报生成与推送。

内容：
1. 自选股当日涨跌幅排行（实时行情，腾讯源）
2. 异动股（涨/跌 ≥5%）
3. 当日触发的预警
4. 今日新增预测观点
5. 持仓盈亏速览

推送：飞书 webhook（notify.send_feishu_message），未配置则只返回文本不报错。
"""
import logging
from datetime import datetime, date

from sqlalchemy import select

from app.db import async_session_maker
from app.models.watchlist import Watchlist
from app.models.position import Position
from app.models.alert import Alert
from app.models.prediction_record import PredictionRecord
from app.services.realtime_service import get_realtime_quotes
from app.services import notify

logger = logging.getLogger(__name__)

ANOMALY_THRESHOLD = 5.0  # 涨/跌 5% 视为异动


async def generate_daily_report() -> str:
    """Build the after-market report text (plain text, Feishu-friendly)."""
    today = date.today().strftime("%Y-%m-%d")
    weekday = date.today().weekday()
    if weekday >= 5:
        return f"📅 {today} 非交易日，无盘后日报。"

    lines: list[str] = [f"📊 自选股盘后日报 {today}", ""]

    # 1. 实时行情（腾讯）
    async with async_session_maker() as db:
        wl = (await db.execute(
            select(Watchlist.stock_code, Watchlist.stock_name).order_by(Watchlist.sort_order)
        )).all()
        positions = {r.stock_code: r for r in
                     (await db.execute(select(Position))).scalars().all()}
        alerts_today = (await db.execute(
            select(Alert).where(Alert.triggered == True)  # noqa: E712
        )).scalars().all()
        preds_today = (await db.execute(
            select(PredictionRecord).where(PredictionRecord.predict_date == today)
        )).scalars().all()

    codes = [c for c, _ in wl]
    name_of = dict(wl)
    quotes_raw = await get_realtime_quotes(codes) if codes else {}
    # 实时源返回键可能带或不带市场前缀，统一映射
    quotes = {}
    for k, v in quotes_raw.items():
        quotes[k] = v
        quotes[f"sh{k}"] = v
        quotes[f"sz{k}"] = v
        quotes[f"bj{k}"] = v

    ranked: list[tuple[str, str, float, float]] = []
    for code in codes:
        q = quotes.get(code) or {}
        price = q.get("price", 0)
        chg = q.get("change_pct", 0)
        ranked.append((code, name_of.get(code, code), chg, price))
    ranked.sort(key=lambda x: -x[2])

    if ranked:
        lines.append("【涨跌幅排行】")
        for code, name, chg, price in ranked:
            arrow = "🔴" if chg > 0 else ("🟢" if chg < 0 else "⚪")
            clean_name = name.replace('\x00', '').strip()
            lines.append(f"{arrow} {clean_name}({code}) {price:.2f}  {chg:+.2f}%")
        lines.append("")

    # 2. 异动
    anomalies = [r for r in ranked if abs(r[2]) >= ANOMALY_THRESHOLD]
    if anomalies:
        lines.append(f"【异动 ≥{ANOMALY_THRESHOLD:.0f}%】")
        for code, name, chg, price in anomalies:
            lines.append(f"⚠️ {name} {chg:+.2f}%")
        lines.append("")

    # 3. 今日触发预警
    alerts_lines = []
    for a in alerts_today:
        if a.triggered_at and a.triggered_at.strftime("%Y-%m-%d") == today:
            desc = f"{a.alert_type}"
            if a.alert_type == "price":
                desc = f"价格{a.direction} {a.target_price}"
            elif a.alert_type == "change_pct":
                desc = f"涨跌幅 {a.pct_threshold:+.1f}%"
            alerts_lines.append(f"🔔 {name_of.get(a.stock_code, a.stock_code)} {desc}")
    if alerts_lines:
        lines.append("【今日预警】")
        lines.extend(alerts_lines)
        lines.append("")

    # 4. 今日预测观点（ensemble 优先）
    seen = {}
    for p in preds_today:
        seen.setdefault(p.stock_code, []).append(p)
    pred_lines = []
    TREND_CN = {"up": "看涨", "bullish": "看涨", "down": "看跌", "bearish": "看跌",
                "flat": "震荡", "neutral": "震荡", "unknown": "待定"}
    for code, recs in seen.items():
        ens = next((r for r in recs if r.model_name == "ensemble"), None)
        if ens and ens.trend != "unknown":
            pred_lines.append(
                f"🔮 {name_of.get(code, code)} → {TREND_CN.get(ens.trend, ens.trend)} "
                f"({ens.horizon_days}日)")
    if pred_lines:
        lines.append("【今日预测观点】")
        lines.extend(pred_lines)
        lines.append("")

    # 5. 持仓盈亏
    pos_lines = []
    total_pnl = 0.0
    for code, pos in positions.items():
        q = quotes.get(code) or {}
        price = q.get("price", 0)
        if not price:
            continue
        pnl = (price - pos.cost_price) * pos.quantity
        pct = (price / pos.cost_price - 1) * 100 if pos.cost_price else 0
        total_pnl += pnl
        pos_lines.append(
            f"💼 {name_of.get(code, pos.stock_name or code)} {pos.quantity}股 "
            f"成本{pos.cost_price:.2f} 现价{price:.2f} {pct:+.1f}% ({pnl:+,.0f}元)")
    if pos_lines:
        lines.append(f"【持仓盈亏】合计 {total_pnl:+,.0f} 元")
        lines.extend(pos_lines)
        lines.append("")

    if len(lines) <= 2:
        lines.append("（今日无行情数据）")

    return "\n".join(lines)


async def send_daily_report() -> dict:
    """Generate the report and push it to Feishu. Returns {text, pushed}."""
    text = await generate_daily_report()
    pushed = False
    try:
        await notify.send_feishu_message(text)
        pushed = True
    except Exception as e:
        logger.warning(f"daily report push failed: {e}")
    logger.info(f"daily report generated ({len(text)} chars, pushed={pushed})")
    return {"text": text, "pushed": pushed, "generated_at": datetime.now().isoformat()}
