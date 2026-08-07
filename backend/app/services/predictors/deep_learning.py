"""F方案: LSTM 深度学习时序预测 — 滑动窗口 60→5 日。"""
import logging
import math
import os
import numpy as np
from datetime import datetime
from sqlalchemy import select
from app.db import async_session_maker
from app.models.kline_data import KlineData

logger = logging.getLogger(__name__)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")


class DeepLearningPredictor:
    def __init__(self):
        self.model = None
        self.scaler_mean = None
        self.scaler_std = None
        os.makedirs(MODEL_DIR, exist_ok=True)

    def _normalize(self, data: list) -> tuple:
        """Z-score 归一化。"""
        arr = np.array(data, dtype=np.float32)
        mean = arr.mean()
        std = arr.std()
        if std == 0:
            std = 1
        normalized = (arr - mean) / std
        return normalized.tolist(), float(mean), float(std)

    def _create_sequences(self, closes: list, seq_len: int = 60, pred_len: int = 5):
        """创建滑动窗口序列。"""
        X, y = [], []
        normalized, mean, std = self._normalize(closes)
        for i in range(seq_len, len(normalized) - pred_len + 1):
            X.append(normalized[i - seq_len:i])
            y.append(normalized[i:i + pred_len])
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32), mean, std

    async def train(self):
        """训练全局 LSTM 模型。"""
        import torch
        import torch.nn as nn

        async with async_session_maker() as db:
            result = await db.execute(
                select(KlineData).order_by(KlineData.stock_code, KlineData.trade_date)
            )
            rows = list(result.scalars().all())

        logger.info(f"加载 {len(rows)} 行数据用于训练")

        # 按股票分组
        stocks = {}
        for r in rows:
            stocks.setdefault(r.stock_code, []).append(r)

        all_X, all_y = [], []
        stock_count = 0
        for code, bars in stocks.items():
            if len(bars) < 120:
                continue
            # 限制每只股票最多 1200 根 K 线用于训练，减少内存
            max_bars = min(len(bars), 1200)
            closes = [b.close for b in bars[-max_bars:]]
            X, y, _, _ = self._create_sequences(closes, 60, 5)
            if len(X) > 0:
                all_X.append(X)
                all_y.append(y)
                stock_count += 1
        logger.info(f"使用 {stock_count} 只股票训练")

        if not all_X:
            logger.warning("训练数据不足")
            return

        X = np.concatenate(all_X, axis=0)
        y = np.concatenate(all_y, axis=0)

        split = int(len(X) * 0.8)
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        logger.info(f"训练样本: {len(X_train)}, 验证样本: {len(X_val)}")

        device = torch.device("cpu")
        logger.info(f"使用设备: {device}")

        X_train_t = torch.tensor(X_train).unsqueeze(-1).to(device)
        y_train_t = torch.tensor(y_train).to(device)
        X_val_t = torch.tensor(X_val).unsqueeze(-1).to(device)
        y_val_t = torch.tensor(y_val).to(device)

        class LSTMPredictor(nn.Module):
            def __init__(self, input_size=1, hidden_size=128, num_layers=2, output_size=5):
                super().__init__()
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
                self.fc = nn.Sequential(
                    nn.Linear(hidden_size, 32),
                    nn.ReLU(),
                    nn.Linear(32, output_size)
                )

            def forward(self, x):
                out, _ = self.lstm(x)
                out = out[:, -1, :]
                return self.fc(out)

        model = LSTMPredictor().to(device)
        criterion = nn.HuberLoss()
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=50)

        batch_size = 64
        n_epochs = 50
        best_val_loss = float('inf')
        patience = 10
        no_improve = 0

        # 如果 MPS 内存不足，降级到 CPU
        if device.type == 'mps':
            try:
                # 测试一个小批量看是否会 OOM
                _ = model(X_train_t[:1])
                torch.mps.empty_cache()
            except RuntimeError:
                logger.warning("MPS OOM，降级到 CPU")
                device = torch.device("cpu")
                X_train_t = X_train_t.cpu()
                y_train_t = y_train_t.cpu()
                X_val_t = X_val_t.cpu()
                y_val_t = y_val_t.cpu()
                model = LSTMPredictor().to(device)
                optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

        logger.info(f"最终使用设备: {device}")

        for epoch in range(n_epochs):
            model.train()
            perm = torch.randperm(len(X_train_t))
            epoch_loss = 0
            n_batches = 0

            for i in range(0, len(X_train_t), batch_size):
                indices = perm[i:i + batch_size]
                X_batch = X_train_t[indices]
                y_batch = y_train_t[indices]

                optimizer.zero_grad()
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            scheduler.step()

            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_t)
                val_loss = criterion(val_outputs, y_val_t).item()

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                no_improve = 0
                torch.save(model.state_dict(), os.path.join(MODEL_DIR, "lstm_global.pt"))
            else:
                no_improve += 1
                if no_improve >= patience:
                    logger.info(f"早停于 epoch {epoch+1}")
                    break

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}/{n_epochs} | train_loss: {epoch_loss/n_batches:.4f} | val_loss: {val_loss:.4f}")

        model.load_state_dict(torch.load(os.path.join(MODEL_DIR, "lstm_global.pt")))
        model.eval()
        self.model = model

        with torch.no_grad():
            preds = model(X_val_t).cpu().numpy()
            actuals = y_val.cpu().numpy()
            pred_direction = (preds[:, -1] > preds[:, 0]).astype(float)
            actual_direction = (actuals[:, -1] > actuals[:, 0]).astype(float)
            direction_acc = (pred_direction == actual_direction).mean()

        logger.info(f"训练完成，方向准确率: {direction_acc:.4f}")
        self.direction_accuracy = float(direction_acc)

    async def predict(self, stock_code: str, days: int = 5) -> dict:
        """对单只股票进行预测。"""
        import torch
        import torch.nn as nn

        if self.model is None:
            model_path = os.path.join(MODEL_DIR, "lstm_global.pt")
            if os.path.exists(model_path):
                class LSTMPredictor(nn.Module):
                    def __init__(self, input_size=1, hidden_size=128, num_layers=2, output_size=5):
                        super().__init__()
                        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
                        self.fc = nn.Sequential(
                            nn.Linear(hidden_size, 32),
                            nn.ReLU(),
                            nn.Linear(32, output_size)
                        )
                    def forward(self, x):
                        out, _ = self.lstm(x)
                        out = out[:, -1, :]
                        return self.fc(out)

                device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
                self.model = LSTMPredictor().to(device)
                self.model.load_state_dict(torch.load(model_path, map_location=device))
                self.model.eval()
            else:
                await self.train()

        if self.model is None:
            return {"forecast": [], "status": "not_trained"}

        async with async_session_maker() as db:
            result = await db.execute(
                select(KlineData).where(KlineData.stock_code == stock_code)
                .order_by(KlineData.trade_date.desc()).limit(100)
            )
            rows = list(result.scalars().all())
            rows.reverse()

        if len(rows) < 60:
            return {"forecast": [], "status": "insufficient_data"}

        closes = [r.close for r in rows]
        current_price = closes[-1]

        normalized, mean, std = self._normalize(closes)
        seq = normalized[-60:]

        device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        X = torch.tensor(seq, dtype=torch.float32).unsqueeze(0).unsqueeze(-1).to(device)

        with torch.no_grad():
            pred_normalized = self.model(X).cpu().numpy()[0]

        pred_prices = [p * std + mean for p in pred_normalized]

        mae = abs(current_price) * 0.03
        forecast = []
        confidence_band = []
        for i, p in enumerate(pred_prices[:days]):
            p = round(max(p, 0), 2)
            forecast.append({"date": f"day_{i+1}", "price": p})
            confidence_band.append({"date": f"day_{i+1}", "low": round(p - 2 * mae, 2), "high": round(p + 2 * mae, 2)})

        return {
            "forecast": forecast,
            "confidence_band": confidence_band,
            "mae": round(mae, 2),
            "direction_accuracy": getattr(self, 'direction_accuracy', 0.5),
            "model_version": "lstm_v1",
            "model_type": "lstm",
            "status": "ok",
            "current_price": round(current_price, 2)
        }