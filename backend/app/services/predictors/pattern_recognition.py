"""E方案: K线形态识别 + 支撑/阻力位。"""
import logging
from sqlalchemy import select
from app.db import async_session_maker
from app.models.kline_data import KlineData

logger = logging.getLogger(__name__)


class PatternRecognizer:
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
        if len(rows) < 60:
            return {"patterns": [], "support": [], "resistance": [], "status": "insufficient_data"}

        closes = [r.close for r in rows]
        highs = [r.high for r in rows]
        lows = [r.low for r in rows]
        opens = [r.open for r in rows]
        dates = [r.trade_date for r in rows]
        current_price = closes[-1]

        patterns = []

        # 1. 双底 / 双顶
        double_pattern = self._detect_double(highs, lows, closes, dates)
        if double_pattern:
            patterns.append(double_pattern)

        # 2. 头肩顶 / 头肩底
        head_shoulder = self._detect_head_shoulder(highs, lows, closes, dates)
        if head_shoulder:
            patterns.append(head_shoulder)

        # 3. 旗形 / 三角整理
        flag = self._detect_flag(highs, lows, closes, dates)
        if flag:
            patterns.append(flag)

        # 4. 吞没形态（最近 10 根）
        engulfing = self._detect_engulfing(opens, closes, dates, len(rows) - 10, len(rows))
        if engulfing:
            patterns.extend(engulfing)

        # 5. 支撑 / 阻力位
        support, resistance = self._find_support_resistance(highs, lows, current_price)

        return {
            "patterns": patterns,
            "support": support,
            "resistance": resistance,
            "status": "ok",
            "current_price": round(current_price, 2),
            "data_date": str(dates[-1])
        }

    def _detect_double(self, highs: list, lows: list, closes: list, dates: list) -> dict | None:
        """检测双底/双顶。"""
        n = len(closes)
        if n < 40:
            return None

        # 找局部低点（双底）
        troughs = []
        for i in range(5, n - 5):
            if all(lows[i] <= lows[i + j] for j in range(-5, 6) if i + j >= 0 and i + j < n):
                troughs.append((i, lows[i]))

        # 配对相近的低点
        for i in range(len(troughs)):
            for j in range(i + 1, len(troughs)):
                idx1, p1 = troughs[i]
                idx2, p2 = troughs[j]
                gap = idx2 - idx1
                if 10 <= gap <= 60:
                    price_diff = abs(p1 - p2) / max(p1, p2)
                    if price_diff < 0.05:  # 价格差 < 5%
                        # 中间高点（颈线）
                        mid_high = max(highs[idx1:idx2 + 1])
                        confidence = min(0.9, 0.5 + (1 - price_diff / 0.05) * 0.4)
                        # 确认方向
                        current_idx = len(closes) - 1
                        if current_idx > idx2:
                            direction = "up" if closes[-1] > mid_high else "down"
                        else:
                            direction = "up"
                        return {
                            "type": "double_bottom",
                            "label": "双底",
                            "start_date": str(dates[idx1]),
                            "end_date": str(dates[idx2]),
                            "confidence": round(confidence, 2),
                            "direction": direction,
                            "neckline": round(mid_high, 2)
                        }

        # 找局部高点（双顶）
        peaks = []
        for i in range(5, n - 5):
            if all(highs[i] >= highs[i + j] for j in range(-5, 6) if i + j >= 0 and i + j < n):
                peaks.append((i, highs[i]))

        for i in range(len(peaks)):
            for j in range(i + 1, len(peaks)):
                idx1, p1 = peaks[i]
                idx2, p2 = peaks[j]
                gap = idx2 - idx1
                if 10 <= gap <= 60:
                    price_diff = abs(p1 - p2) / max(p1, p2)
                    if price_diff < 0.05:
                        mid_low = min(lows[idx1:idx2 + 1])
                        confidence = min(0.9, 0.5 + (1 - price_diff / 0.05) * 0.4)
                        current_idx = len(closes) - 1
                        direction = "down" if current_idx > idx2 and closes[-1] < mid_low else "down"
                        return {
                            "type": "double_top",
                            "label": "双顶",
                            "start_date": str(dates[idx1]),
                            "end_date": str(dates[idx2]),
                            "confidence": round(confidence, 2),
                            "direction": direction,
                            "neckline": round(mid_low, 2)
                        }
        return None

    def _detect_head_shoulder(self, highs: list, lows: list, closes: list, dates: list) -> dict | None:
        """检测头肩顶/头肩底。"""
        n = len(closes)
        if n < 60:
            return None

        peaks = []
        for i in range(3, n - 3):
            if all(highs[i] >= highs[i + j] for j in range(-3, 4) if i + j >= 0 and i + j < n):
                peaks.append((i, highs[i]))

        if len(peaks) < 3:
            return None

        # 找三个依次的峰，中间最高
        for i in range(len(peaks) - 2):
            left = peaks[i]
            head = peaks[i + 1]
            right = peaks[i + 2]
            if head[1] > left[1] and head[1] > right[1]:
                gap = head[0] - left[0]
                gap2 = right[0] - head[0]
                if 10 <= gap <= 40 and 10 <= gap2 <= 40:
                    # 颈线 = 左肩低点和右肩低点的连线
                    left_trough = min(lows[left[0]:head[0] + 1])
                    right_trough = min(lows[head[0]:right[0] + 1])
                    neckline = (left_trough + right_trough) / 2
                    current_idx = len(closes) - 1
                    if current_idx > right[0] and closes[-1] < neckline:
                        return {
                            "type": "head_and_shoulders_top",
                            "label": "头肩顶",
                            "start_date": str(dates[left[0]]),
                            "end_date": str(dates[right[0]]),
                            "confidence": 0.7,
                            "direction": "down",
                            "neckline": round(neckline, 2)
                        }
        return None

    def _detect_flag(self, highs: list, lows: list, closes: list, dates: list) -> dict | None:
        """检测旗形/三角整理。"""
        n = len(closes)
        if n < 30:
            return None

        # 看最近 30 根 K 线是否在收敛（三角整理）
        recent_highs = highs[-30:]
        recent_lows = lows[-30:]
        high_slope = (recent_highs[-1] - recent_highs[0]) / 30
        low_slope = (recent_lows[-1] - recent_lows[0]) / 30

        # 三角整理：高点下降 + 低点上升
        if high_slope < -0.001 and low_slope > 0.001:
            width = (recent_highs[-1] - recent_lows[-1]) / closes[-1]
            if width < 0.15:  # 收敛到 15% 以内
                return {
                    "type": "triangle",
                    "label": "三角整理",
                    "start_date": str(dates[-30]),
                    "end_date": str(dates[-1]),
                    "confidence": 0.55,
                    "direction": "up" if closes[-1] > recent_highs[0] else "down"
                }

        # 旗形：快速涨跌后小幅回调
        if n >= 40:
            early_high = max(highs[-40:-20])
            early_low = min(lows[-40:-20])
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
            if early_high > recent_high and early_low < recent_low:
                return {
                    "type": "bull_flag",
                    "label": "上升旗形",
                    "start_date": str(dates[-40]),
                    "end_date": str(dates[-1]),
                    "confidence": 0.5,
                    "direction": "up"
                }
        return None

    def _detect_engulfing(self, opens: list, closes: list, dates: list, start: int, end: int) -> list:
        """检测吞没形态。"""
        results = []
        for i in range(max(1, start), min(end, len(closes))):
            prev_open, prev_close = opens[i - 1], closes[i - 1]
            curr_open, curr_close = opens[i], closes[i]
            prev_body = abs(prev_close - prev_open)
            curr_body = abs(curr_close - curr_open)
            if prev_body == 0 or curr_body == 0:
                continue

            # 看涨吞没：阴线后被阳线完全覆盖
            if prev_close < prev_open and curr_close > curr_open:
                if curr_open < prev_close and curr_close > prev_open:
                    results.append({
                        "type": "bullish_engulfing",
                        "label": "看涨吞没",
                        "start_date": str(dates[i - 1]),
                        "end_date": str(dates[i]),
                        "confidence": 0.6,
                        "direction": "up"
                    })

            # 看跌吞没：阳线后被阴线完全覆盖
            if prev_close > prev_open and curr_close < curr_open:
                if curr_open > prev_close and curr_close < prev_open:
                    results.append({
                        "type": "bearish_engulfing",
                        "label": "看跌吞没",
                        "start_date": str(dates[i - 1]),
                        "end_date": str(dates[i]),
                        "confidence": 0.6,
                        "direction": "down"
                    })
        return results

    def _find_support_resistance(self, highs: list, lows: list, current_price: float) -> tuple:
        """支撑/阻力位识别：价格区间触碰次数统计。"""
        if not highs or not lows:
            return [], []

        # 价格范围
        all_prices = highs + lows
        price_min = min(all_prices)
        price_max = max(all_prices)
        step = (price_max - price_min) / 50  # 50 个区间
        if step == 0:
            return [], []

        # 统计每个区间被触碰的次数
        buckets = {}
        for i in range(51):
            buckets[i] = {"count": 0, "last_idx": -999}

        for i in range(len(highs)):
            # 高点触碰
            h_bucket = int((highs[i] - price_min) / step)
            if h_bucket >= 0 and h_bucket <= 50:
                if i - buckets[h_bucket]["last_idx"] > 5:  # 间隔 > 5 根 K 线才算有效触碰
                    buckets[h_bucket]["count"] += 1
                    buckets[h_bucket]["last_idx"] = i
            # 低点触碰
            l_bucket = int((lows[i] - price_min) / step)
            if l_bucket >= 0 and l_bucket <= 50:
                if i - buckets[l_bucket]["last_idx"] > 5:
                    buckets[l_bucket]["count"] += 1
                    buckets[l_bucket]["last_idx"] = i

        # 筛选触碰次数 >= 3 的区间
        support = []
        resistance = []
        for bucket_idx, info in buckets.items():
            if info["count"] >= 3:
                price = round(price_min + (bucket_idx + 0.5) * step, 2)
                if price < current_price:
                    support.append({"price": price, "strength": round(min(info["count"] / 10, 1), 2), "touches": info["count"]})
                elif price > current_price:
                    resistance.append({"price": price, "strength": round(min(info["count"] / 10, 1), 2), "touches": info["count"]})

        # 按 strength 排序取前 3
        support.sort(key=lambda x: x["strength"], reverse=True)
        resistance.sort(key=lambda x: x["strength"], reverse=True)

        return support[:3], resistance[:3]