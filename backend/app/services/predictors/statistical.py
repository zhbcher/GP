"""B方案: 统计模型预测 — 线性回归趋势线外推 + 指数平滑。"""
import logging
import math
from sqlalchemy import select
from app.db import async_session_maker
from app.models.kline_data import KlineData

logger = logging.getLogger(__name__)


class StatisticalPredictor:
    async def predict(self, stock_code: str, days: int = 5) -> dict:
        async with async_session_maker() as db:
            result = await db.execute(
                select(KlineData).where(KlineData.stock_code == stock_code)
                .order_by(KlineData.trade_date.desc()).limit(150)
            )
            rows = list(result.scalars().all())
        rows.reverse()
        return self._predict_from_rows(rows, days)

    def _predict_from_rows(self, rows, days: int = 5) -> dict:
        if len(rows) < 30:
            return {"forecast": [], "status": "insufficient_data"}

        closes = [r.close for r in rows]
        from datetime import datetime, timedelta
        dates = [r.trade_date for r in rows]
        last_date = datetime.strptime(str(dates[-1]), '%Y-%m-%d').date() if isinstance(dates[-1], str) else dates[-1]
        current_price = closes[-1]

        # 1. 线性回归（近 60 日）
        reg_result = self._linear_regression(closes[-60:], days)

        # 2. 指数平滑
        smooth_result = self._exponential_smoothing(closes, days)

        # 3. 综合
        forecast = []
        for i in range(days):
            reg_price = reg_result["forecast"][i]
            smooth_price = smooth_result["forecast"][i]
            price = round(0.4 * reg_price + 0.6 * smooth_price, 2)
            # 使用实际日期（外推）
            next_date = (last_date + timedelta(days=i + 1)).strftime('%Y-%m-%d')
            forecast.append({"date": str(next_date), "price": price})

        # 置信区间
        line_vals = reg_result["line_values"]
        if line_vals and len(closes[-60:]) > 0:
            min_len = min(len(closes[-60:]), len(line_vals))
            residuals = [abs(closes[-60:][i] - line_vals[i]) for i in range(min_len)]
            mae = sum(residuals) / len(residuals) if residuals else current_price * 0.02
        else:
            mae = current_price * 0.02
        range_low = round(min(f["price"] for f in forecast) - 2 * mae, 2)
        range_high = round(max(f["price"] for f in forecast) + 2 * mae, 2)

        trend = "up" if forecast[-1]["price"] > current_price else "down" if forecast[-1]["price"] < current_price else "sideways"

        return {
            "forecast": forecast,
            "range_low": range_low,
            "range_high": range_high,
            "r2": round(reg_result["r2"], 4),
            "trend": trend,
            "mae": round(mae, 2),
            "status": "ok",
            "current_price": round(current_price, 2)
        }

    def _linear_regression(self, data: list, days: int) -> dict:
        n = len(data)
        if n < 2:
            return {"forecast": [data[-1]] * days, "line_values": data, "r2": 0}
        x = list(range(n))
        y = data
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        den = sum((x[i] - x_mean) ** 2 for i in range(n))
        slope = num / den if den != 0 else 0
        intercept = y_mean - slope * x_mean

        y_pred = [slope * xi + intercept for xi in x]
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        forecast = [slope * (n + i) + intercept for i in range(days)]

        return {"forecast": forecast, "line_values": y_pred, "r2": r2, "slope": slope}

    def _exponential_smoothing(self, data: list, days: int) -> dict:
        if len(data) < 10:
            return {"forecast": [data[-1]] * days}

        level = data[-1]
        trend = (data[-1] - data[-min(10, len(data))]) / min(10, len(data))

        alpha = 0.3
        beta = 0.1

        for i in range(len(data) - 2, -1, -1):
            prev_level = level
            level = alpha * data[i] + (1 - alpha) * (level - trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend

        forecast = [level + (i + 1) * trend for i in range(days)]
        forecast = [max(f, 0) for f in forecast]

        return {"forecast": forecast}