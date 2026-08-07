"""A方案: 技术指标预测 — 基于 MA/MACD/BOLL/RSI/KDJ 的短期趋势判断。"""
import logging
import math
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.db import async_session_maker
from app.models.kline_data import KlineData

logger = logging.getLogger(__name__)


class TechnicalPredictor:
    """基于技术指标的短期趋势预测。"""

    async def predict(self, stock_code: str, days: int = 5) -> dict:
        async with async_session_maker() as db:
            # 取近 120 根日 K（需要 60 根计算指标，多取一些做平滑）
            result = await db.execute(
                select(KlineData)
                .where(KlineData.stock_code == stock_code)
                .order_by(KlineData.trade_date.desc())
                .limit(120)
            )
            rows = list(result.scalars().all())
        rows.reverse()  # 时间升序

        if len(rows) < 60:
            return {
                "trend": "unknown",
                "confidence": 0,
                "signals": {},
                "status": "insufficient_data",
            }

        closes = [r.close for r in rows]
        highs = [r.high for r in rows]
        lows = [r.low for r in rows]
        volumes = [r.volume for r in rows]
        dates = [r.trade_date for r in rows]
        current_price = closes[-1]

        # 计算各项指标
        signals = {}

        # 1. MA 系统
        ma5 = self._sma(closes, 5)
        ma20 = self._sma(closes, 20)
        ma60 = self._sma(closes, 60)
        ma5_slope = self._slope(ma5, 3)
        ma20_slope = self._slope(ma20, 5)

        ma_signal = "neutral"
        if ma5[-1] > ma20[-1] > ma60[-1]:
            ma_signal = "bullish"
        elif ma5[-1] < ma20[-1] < ma60[-1]:
            ma_signal = "bearish"
        signals["ma"] = ma_signal
        signals["ma5"] = round(ma5[-1], 2) if ma5[-1] else 0
        signals["ma20"] = round(ma20[-1], 2) if ma20[-1] else 0
        signals["ma5_slope"] = round(ma5_slope, 4)
        signals["ma20_slope"] = round(ma20_slope, 4)

        # 2. MACD
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)

        dif_list = [ema12[i] - ema26[i] for i in range(len(ema12))]
        dea_list = self._ema_list(dif_list, 9)

        macd_hist = 2 * (dif_list[-1] - dea_list[-1])
        macd_prev_hist = (
            2 * (dif_list[-2] - dea_list[-2]) if len(dif_list) > 1 else 0
        )

        macd_signal = "neutral"
        if dif_list[-1] > dea_list[-1] and dif_list[-2] <= dea_list[-2]:
            macd_signal = "golden_cross"
        elif dif_list[-1] < dea_list[-1] and dif_list[-2] >= dea_list[-2]:
            macd_signal = "dead_cross"
        elif dif_list[-1] > dea_list[-1]:
            macd_signal = "bullish"
        elif dif_list[-1] < dea_list[-1]:
            macd_signal = "bearish"
        signals["macd"] = macd_signal
        signals["macd_dif"] = round(dif_list[-1], 2)
        signals["macd_dea"] = round(dea_list[-1], 2)
        signals["macd_hist"] = round(macd_hist, 2)

        # 3. 布林带
        bb_mid = self._sma(closes, 20)[-1]
        bb_std = self._std(closes, 20)
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid else 0

        boll_signal = "neutral"
        if current_price >= bb_upper:
            boll_signal = "upper"
        elif current_price <= bb_lower:
            boll_signal = "lower"
        elif current_price > bb_mid:
            boll_signal = "mid_above"
        else:
            boll_signal = "mid_below"
        signals["boll"] = boll_signal
        signals["boll_upper"] = round(bb_upper, 2)
        signals["boll_mid"] = round(bb_mid, 2)
        signals["boll_lower"] = round(bb_lower, 2)
        signals["boll_width"] = round(bb_width, 4)

        # 4. RSI(14)
        rsi = self._rsi(closes, 14)

        rsi_signal = "normal"
        if rsi > 70:
            rsi_signal = "overbought"
        elif rsi < 30:
            rsi_signal = "oversold"

        # RSI 背离检测
        divergence = self._check_rsi_divergence(closes, rsi, 14)
        if divergence:
            rsi_signal = divergence
        signals["rsi"] = round(rsi, 2)
        signals["rsi_signal"] = rsi_signal

        # 5. KDJ
        k, d, j = self._kdj(highs, lows, closes, 9)

        kdj_signal = "neutral"
        if k[-1] > d[-1] and k[-2] <= d[-2]:
            kdj_signal = "golden_cross"
        elif k[-1] < d[-1] and k[-2] >= d[-2]:
            kdj_signal = "dead_cross"
        elif j[-1] > 100:
            kdj_signal = "overbought"
        elif j[-1] < 0:
            kdj_signal = "oversold"
        signals["kdj"] = kdj_signal
        signals["kdj_k"] = round(k[-1], 2)
        signals["kdj_d"] = round(d[-1], 2)
        signals["kdj_j"] = round(j[-1], 2)

        # 综合趋势判断
        bullish_count = 0
        bearish_count = 0
        total_signals = 0
        for key in ["ma", "macd", "boll", "kdj"]:
            val = signals.get(key, "neutral")
            if val in ("bullish", "golden_cross", "mid_above"):
                bullish_count += 1
            elif val in ("bearish", "dead_cross", "mid_below"):
                bearish_count += 1
            total_signals += 1

        # RSI 单独判断
        if rsi_signal == "oversold" or rsi_signal == "divergence_bullish":
            bullish_count += 1
        elif rsi_signal == "overbought" or rsi_signal == "divergence_bearish":
            bearish_count += 1
        total_signals += 1

        if bullish_count > bearish_count:
            trend = "up"
            confidence = bullish_count / total_signals
        elif bearish_count > bullish_count:
            trend = "down"
            confidence = bearish_count / total_signals
        else:
            trend = "sideways"
            confidence = 0.5

        return {
            "trend": trend,
            "confidence": round(confidence, 2),
            "signals": signals,
            "status": "ok",
            "current_price": round(current_price, 2),
            "data_date": str(dates[-1]),
        }

    # --- 工具函数 ---
    def _sma(self, data: list, period: int) -> list:
        if len(data) < period:
            return [0] * len(data)
        result = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(0)
            else:
                result.append(sum(data[i - period + 1 : i + 1]) / period)
        return result

    def _ema(self, data: list, period: int) -> list:
        if len(data) < period:
            return [0] * len(data)
        result = []
        multiplier = 2 / (period + 1)
        # 第一个 EMA = SMA
        ema = sum(data[:period]) / period
        result.extend([0] * (period - 1))
        result.append(ema)
        for i in range(period, len(data)):
            ema = (data[i] - ema) * multiplier + ema
            result.append(ema)
        return result

    def _ema_single(self, data: list, period: int) -> float:
        if len(data) < period:
            return data[-1] if data else 0
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        for i in range(period, len(data)):
            ema = (data[i] - ema) * multiplier + ema
        return ema

    def _ema_list(self, data: list, period: int) -> list:
        if len(data) < period:
            return [0] * len(data)
        result = [0] * (period - 1)
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        result.append(ema)
        for i in range(period, len(data)):
            ema = (data[i] - ema) * multiplier + ema
            result.append(ema)
        return result

    def _slope(self, data: list, period: int) -> float:
        valid = [x for x in data[-period:] if x != 0]
        if len(valid) < 2:
            return 0
        return (valid[-1] - valid[0]) / len(valid)

    def _std(self, data: list, period: int) -> float:
        if len(data) < period:
            return 0
        segment = data[-period:]
        mean = sum(segment) / period
        variance = sum((x - mean) ** 2 for x in segment) / period
        return math.sqrt(variance)

    def _rsi(self, data: list, period: int) -> float:
        if len(data) < period + 1:
            return 50
        gains = 0
        losses = 0
        for i in range(-period, 0):
            diff = data[i] - data[i - 1]
            if diff > 0:
                gains += diff
            else:
                losses -= diff
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _check_rsi_divergence(self, prices: list, rsi_val: float, period: int) -> str:
        if len(prices) < period * 2:
            return ""
        recent_prices = prices[-period:]
        if len(recent_prices) < 5:
            return ""
        # 简单背离检测：价格创新低但RSI未创新低 → 底背离
        price_min = min(recent_prices)
        price_min_idx = recent_prices.index(price_min)
        if price_min_idx > 0:
            prev_min = min(recent_prices[:price_min_idx])
            if price_min < prev_min:
                return "divergence_bullish"
        return ""

    def _kdj(self, highs: list, lows: list, closes: list, period: int) -> tuple:
        if len(closes) < period:
            return [50] * len(closes), [50] * len(closes), [50] * len(closes)
        k_vals = []
        d_vals = []
        j_vals = []
        k = 50
        d = 50
        for i in range(len(closes)):
            if i < period - 1:
                k_vals.append(50)
                d_vals.append(50)
                j_vals.append(50)
                continue
            hh = max(highs[i - period + 1 : i + 1])
            ll = min(lows[i - period + 1 : i + 1])
            if hh == ll:
                rsv = 50
            else:
                rsv = (closes[i] - ll) / (hh - ll) * 100
            k = 2 / 3 * k + 1 / 3 * rsv
            d = 2 / 3 * d + 1 / 3 * k
            j = 3 * k - 2 * d
            k_vals.append(k)
            d_vals.append(d)
            j_vals.append(j)
        return k_vals, d_vals, j_vals
