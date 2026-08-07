"""C方案: 蒙特卡洛模拟 — 基于历史收益率 bootstrap 的未来价格概率分布。"""
import logging
import random
import math
from sqlalchemy import select
from app.db import async_session_maker
from app.models.kline_data import KlineData

logger = logging.getLogger(__name__)


class MonteCarloPredictor:
    async def predict(self, stock_code: str, days: int = 5) -> dict:
        async with async_session_maker() as db:
            result = await db.execute(
                select(KlineData).where(KlineData.stock_code == stock_code)
                .order_by(KlineData.trade_date.desc()).limit(100)
            )
            rows = list(result.scalars().all())
        rows.reverse()
        return self._predict_from_rows(rows, days)

    def _predict_from_rows(self, rows, days: int = 5) -> dict:
        if len(rows) < 20:
            return {"median": 0, "range_low": 0, "range_high": 0, "status": "insufficient_data"}

        closes = [r.close for r in rows]
        current_price = closes[-1]

        # 计算收益率
        returns = []
        for i in range(1, len(closes)):
            r = math.log(closes[i] / closes[i - 1])
            if abs(r) < 0.3:
                returns.append(r)

        if len(returns) < 10:
            return {"median": current_price, "range_low": current_price * 0.98,
                    "range_high": current_price * 1.02, "status": "insufficient_data"}

        mu = sum(returns) / len(returns)
        sigma = math.sqrt(sum((r - mu) ** 2 for r in returns) / len(returns))

        NUM_SIMULATIONS = 10000
        final_prices = []

        for _ in range(NUM_SIMULATIONS):
            price = current_price
            for _ in range(days):
                r = random.choice(returns)
                price *= math.exp(r)
            final_prices.append(price)

        final_prices.sort()

        median = final_prices[NUM_SIMULATIONS // 2]
        range_low = final_prices[int(NUM_SIMULATIONS * 0.1)]
        range_high = final_prices[int(NUM_SIMULATIONS * 0.9)]
        up_count = sum(1 for p in final_prices if p > current_price)
        up_probability = up_count / NUM_SIMULATIONS

        return {
            "median": round(median, 2),
            "range_low": round(range_low, 2),
            "range_high": round(range_high, 2),
            "up_probability": round(up_probability, 4),
            "samples": NUM_SIMULATIONS,
            "daily_volatility": round(sigma, 4),
            "annualized_volatility": round(sigma * math.sqrt(252), 4),
            "status": "ok",
            "current_price": round(current_price, 2)
        }