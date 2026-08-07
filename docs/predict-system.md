# 综合预测系统 — 技术方案

> 版本: v1.0
> 日期: 2026-08-01
> 项目: ~/GP 自选股看盘系统
> 前置: 数据扩充（自选股数量 + 全量历史数据拉取）

---

## 一、系统概述

在现有 K 线图基础上，集成 7 种预测模型，从纯数学到深度学习再到 LLM 分析，形成多模型投票融合的综合预测系统。

### 1.1 核心原则

- **渐进式**：Phase 1~2 无依赖即可上线，Phase 3~7 逐步叠加
- **可解释**：每个模型输出独立结果，融合器只做投票加权，不做黑盒
- **本地运行**：全部在 Mac mini M4 上运行，无外部服务依赖（G 方案除外）
- **数据驱动**：Phase 3 数据扩充是所有 ML/DL 方案的前提

---

## 二、7 种方案详细设计

### 2.1 A 方案 — 技术指标预测

**定位**：最快、最稳、零依赖。基于已有技术指标判断短期趋势。

**输入**：近 60 根日 K 的 OHLCV

**算法**：

```
1. 均线系统
   - MA5 斜率 > 0 → 短期多头
   - MA20 斜率 > 0 → 中期多头
   - MA5 > MA20 > MA60 → 多头排列
   - MA5 < MA20 < MA60 → 空头排列

2. MACD
   - DIF 上穿 DEA → 金叉（看多）
   - DIF 下穿 DEA → 死叉（看空）
   - MACD 柱由负转正 → 动量转多

3. 布林带
   - 价格触及下轨 + RSI < 30 → 超卖反弹信号
   - 价格触及上轨 + RSI > 70 → 超买回调信号
   - 布林带收窄 → 变盘信号

4. RSI(14)
   - RSI < 30 → 超卖
   - RSI > 70 → 超买
   - RSI 底背离（价格新低，RSI 未新低）→ 反转看多
   - RSI 顶背离（价格新高，RSI 未新高）→ 反转看空

5. KDJ
   - K 上穿 D → 金叉
   - K 下穿 D → 死叉
   - J > 100 → 超买
   - J < 0 → 超卖
```

**输出**：
```json
{
  "trend": "up",           // up / down / sideways
  "confidence": 0.65,      // 0~1
  "signals": {
    "ma": "bullish",       // bullish / bearish / neutral
    "macd": "golden_cross", // golden_cross / dead_cross / neutral
    "boll": "mid_above",   // upper / mid_above / mid_below / lower
    "rsi": 55.2,           // 数值
    "rsi_signal": "normal", // oversold / overbought / normal / divergence
    "kdj": "golden_cross"
  }
}
```

**实现文件**：`backend/app/services/predictors/technical.py`

---

### 2.2 B 方案 — 统计模型预测

**定位**：基于经典时间序列方法，给出未来 N 日价格区间。

**依赖**：statsmodels（pip install statsmodels）

**输入**：近 120 根日 K 的收盘价序列

**算法**：

```
1. ARIMA 模型
   - 自动定阶 (p,d,q)：用 AIC 准则在 [0,5]×[0,2]×[0,5] 范围内搜索
   - 训练：ARIMA(p,d,q) 拟合近 120 日数据
   - 预测：外推未来 5 日，输出点估计 + 置信区间
   - 回退：如果 ARIMA 拟合失败，降级为简单指数平滑

2. 线性回归趋势线
   - 用近 20/60/120 日收盘价分别拟合线性回归
   - 取斜率 = 趋势方向
   - 外推 5 日
   - 20 日斜率敏感（短期），120 日斜率稳定（长期）

3. 综合
   - ARIMA 预测作为主要价格预测
   - 线性回归斜率作为趋势确认
   - 置信区间取 ARIMA 的 95% CI
```

**输出**：
```json
{
  "forecast": [
    {"date": "2026-08-03", "price": 1462.5},
    {"date": "2026-08-04", "price": 1468.2},
    {"date": "2026-08-05", "price": 1455.8},
    {"date": "2026-08-06", "price": 1460.1},
    {"date": "2026-08-07", "price": 1465.3}
  ],
  "range_low": 1420.0,
  "range_high": 1510.0,
  "r2": 0.72,            // 拟合优度
  "model": "ARIMA(2,1,2)",
  "trend": "up"
}
```

**实现文件**：`backend/app/services/predictors/statistical.py`

---

### 2.3 C 方案 — 蒙特卡洛模拟

**定位**：基于历史波动率，通过大量随机模拟给出概率分布。

**依赖**：无（纯 numpy）

**输入**：近 60 根日 K 的收益率序列

**算法**：

```
1. 计算近 60 日对数收益率
   μ = mean(ln(P_t / P_{t-1}))
   σ = std(ln(P_t / P_{t-1}))

2. 模拟 10000 条路径，每条 5 步
   for i in 10000:
     price = current_price
     for day in 5:
       ε ~ N(0, 1)
       price *= exp(μ + σ * ε)
     paths[i] = price

3. 统计
   median = 中位数(最终价格)
   range_low = 百分位(最终价格, 10%)   // 80% 置信区间下限
   range_high = 百分位(最终价格, 90%)  // 80% 置信区间上限
   up_prob = count(最终价格 > 当前价) / 10000

4. 增强：收益率分布用实际历史分布（非正态假设）
   - 从近 60 日收益率中 bootstrap 抽样（放回），替代 N(0,1) 假设
   - 更准确反映肥尾特性
```

**输出**：
```json
{
  "median": 1465.0,
  "range_low": 1420.0,
  "range_high": 1510.0,
  "up_probability": 0.62,
  "samples": 10000,
  "daily_volatility": 0.018,
  "annualized_volatility": 0.286
}
```

**实现文件**：`backend/app/services/predictors/monte_carlo.py`

---

### 2.4 D 方案 — 轻量 ML（XGBoost）

**定位**：通过特征工程 + 树模型，预测次日涨跌方向。

**依赖**：xgboost, scikit-learn, pandas

**输入**：近 N 日 K 线 + 衍生特征

**特征工程**（约 40 个特征）：

```
价格特征:
  - close / MA5, close / MA20, close / MA60
  - MA5 - MA20, MA20 - MA60（均线差）
  - 近 1/5/20 日收益率
  - 近 5 日价格波动率

成交量特征:
  - volume / MA5_volume
  - 近 5 日成交量变化率
  - 量价配合（涨时放量/跌时放量）

技术指标特征:
  - RSI(14), KDJ_K, KDJ_D, KDJ_J
  - MACD_DIF, MACD_DEA, MACD_HIST
  - BOLL_upper, BOLL_lower, BOLL_mid, BOLL_%

日期特征:
  - 星期几（周一~周五）
  - 月份
  - 季度末标志
  - 月初/月末

标签:
  - 次日涨跌（二分类：1=涨, 0=跌）
  - 或 未来 5 日涨跌幅（回归）
```

**训练策略**：

```
1. 全局模型：用所有股票数据训练一个通用模型
   - 训练集：前 80% 时间
   - 验证集：后 20% 时间
   - 参数：n_estimators=200, max_depth=6, learning_rate=0.1
   - 早停：验证集 10 轮无改善停止

2. 个股模型：在全局模型基础上用个股数据微调
   - 用全局模型的前 5 棵树作为基础
   - 个股数据继续训练 50 棵树
   - 防止小样本过拟合

3. 定时重训：每周收盘后重训

4. 评估：
   - 方向准确率（Direction Accuracy）
   - 精确率/召回率/F1
   - 混淆矩阵
   - 特征重要性排名
```

**输出**：
```json
{
  "up_probability": 0.58,
  "signal": "hold",          // buy / sell / hold
  "direction_accuracy": 0.53,
  "feature_importance": {
    "ma_slope_5": 0.23,
    "volume_ratio": 0.18,
    "rsi_14": 0.15,
    "macd_hist": 0.12,
    "close_ma5_ratio": 0.10
  },
  "model_version": "xgb_v1",
  "trained_on": "2026-08-01",
  "samples": 45000
}
```

**实现文件**：`backend/app/services/predictors/xgboost_predictor.py`

---

### 2.5 E 方案 — K 线形态识别

**定位**：识别经典 K 线形态，辅助判断趋势反转/延续。

**依赖**：无（纯数学）

**输入**：近 120 根日 K 的 OHLCV

**算法**：

```
1. 支撑/阻力位识别
   - 将价格范围分为 N 个区间（步长 = 价格 * 0.5%）
   - 统计每个区间被 K 线 high/low 触碰的次数
   - 触碰次数 > 阈值（3次）且间隔 > 5 根 K 线 → 标记为支撑/阻力位
   - 近期的触碰权重更高

2. 双底 / 双顶
   - 找两个相近的低点（价格差 < 5%，间隔 10~40 根 K 线）
   - 中间有一个高点（颈线）
   - 突破颈线 → 确认

3. 头肩顶 / 头肩底
   - 左肩（局部高点）→ 头部（更高高点）→ 右肩（略低高点）
   - 颈线连接左肩和右肩的低点
   - 跌破颈线 → 确认

4. 旗形 / 三角整理
   - 快速上涨/下跌后，价格在两条收敛趋势线内整理
   - 向上突破上轨 → 上涨旗形
   - 向下突破下轨 → 下跌旗形

5. 吞没形态
   - 阳线实体完全覆盖前一根阴线实体 → 看涨吞没
   - 阴线实体完全覆盖前一根阳线实体 → 看跌吞没

6. 置信度评分
   - 形态完整度（是否符合标准形态）→ 0~1
   - 成交量配合（突破时放量）→ 加分
   - 位置（在支撑/阻力位附近）→ 加分
```

**输出**：
```json
{
  "patterns": [
    {
      "type": "double_bottom",
      "label": "双底",
      "start_date": "2026-06-15",
      "end_date": "2026-07-10",
      "confidence": 0.75,
      "direction": "up"
    },
    {
      "type": "bull_flag",
      "label": "上升旗形",
      "start_date": "2026-07-20",
      "end_date": "2026-07-31",
      "confidence": 0.6,
      "direction": "up"
    }
  ],
  "support": [
    {"price": 1420.0, "strength": 0.8, "touches": 5},
    {"price": 1380.0, "strength": 0.6, "touches": 3}
  ],
  "resistance": [
    {"price": 1480.0, "strength": 0.7, "touches": 4},
    {"price": 1520.0, "strength": 0.5, "touches": 2}
  ]
}
```

**实现文件**：`backend/app/services/predictors/pattern_recognition.py`

---

### 2.6 F 方案 — 深度学习（LSTM / Transformer）

**定位**：最强大的预测模型，学习复杂时序模式，输出未来价格序列。

**依赖**：torch（MPS 加速）

**输入**：近 60 根日 K 的 OHLCV + 成交量 + 技术指标（归一化后）

**模型架构**：

```
┌─────────────────────────────────────────────┐
│             输入层                           │
│  形状: [batch, 60, features]                │
│  features: OHLCV(5) + 技术指标(5) + 日期(2)  │
│  = 12 维                                     │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────▼──────────┐
        │   LSTM 方案          │
        │                     │
        │  LSTM(128, return_seq)  │
        │  Dropout(0.2)        │
        │  LSTM(64)            │
        │  Dropout(0.2)        │
        │  Dense(32, ReLU)     │
        │  Dense(5)            │
        │  ↑ 未来5日收盘价      │
        └─────────────────────┘

        ┌──────────▼──────────┐
        │   Transformer 方案    │
        │                     │
        │  PositionalEncoding  │
        │  TransformerEncoder  │
        │  × 2 layers          │
        │  (d_model=64, nhead=4)│
        │  GlobalAvgPooling    │
        │  Dense(5)            │
        └─────────────────────┘
```

**训练策略**：

```
1. 数据预处理
   - 归一化：MinMaxScaler 每只股票独立归一化
   - 滑动窗口：窗口=60, 步长=1, 标签=未来5日收盘价
   - 单只股票 1000 根 → 约 940 个样本
   - 50 只股票 5000 根 → 约 250000 个样本

2. 模型训练
   - 全局模型 + 个股微调（与 XGBoost 策略相同）
   - 损失函数：Huber Loss（对异常值鲁棒）
   - 优化器：AdamW (lr=1e-3, weight_decay=1e-4)
   - 学习率调度：CosineAnnealingLR
   - 早停：验证集 MAE 20 轮无改善
   - Batch Size: 64
   - Epochs: 100（含早停约 30~50）

3. M4 芯片适配
   - device = "mps"（Metal Performance Shaders）
   - 单只股票训练约 1~2 分钟
   - 50 只股票全局模型约 5~10 分钟
   - 推理 < 100ms

4. 评估
   - MAE（平均绝对误差）
   - RMSE（均方根误差）
   - 方向准确率（预测方向 vs 实际方向）
   - 回测：walk-forward 验证（每 6 个月滚动）
```

**输出**：
```json
{
  "forecast": [
    {"date": "2026-08-03", "price": 1465.0},
    {"date": "2026-08-04", "price": 1472.0},
    {"date": "2026-08-05", "price": 1460.0},
    {"date": "2026-08-06", "price": 1468.0},
    {"date": "2026-08-07", "price": 1475.0}
  ],
  "confidence_band": [
    {"date": "2026-08-03", "low": 1440.0, "high": 1490.0},
    ...
  ],
  "mae": 12.5,
  "direction_accuracy": 0.55,
  "model_version": "lstm_v1",
  "model_type": "lstm",
  "trained_on": "2026-08-01"
}
```

**实现文件**：`backend/app/services/predictors/deep_learning.py`

---

### 2.7 G 方案 — LLM 综合分析

**定位**：将各模型结果 + K 线数据输入 LLM，生成人类可读的分析报告。

**依赖**：有效的 LLM API key（OpenAI / DeepSeek / NVIDIA 兼容 API）

**输入**（压缩后的文本）：

```
近 60 日 K 线摘要（OHLCV 周粒度）
技术指标当前值（MA, MACD, RSI, BOLL, KDJ）
各模型预测结果（A~F 的投票 + 置信度）
形态识别结果
支撑/阻力位
```

**Prompt 模板**：

```
你是一个A股技术分析师。请基于以下数据给出分析：

## 股票信息
- 股票：{stock_name} ({stock_code})
- 当前价：{current_price}
- 近60日涨跌幅：{change_pct}%

## 技术指标
{technical_signals_text}

## 各模型预测
{model_ensemble_text}

## 形态识别
{pattern_text}

## 支撑/阻力
{support_resistance_text}

请输出：
1. 趋势判断（看涨/看跌/震荡）及理由
2. 关键价位（支撑/阻力）
3. 操作建议
4. 风险提示
5. 置信度（0~100%）
```

**输出**：
```json
{
  "summary": "近60日走势呈上升旗形整理，成交量逐步萎缩，均线多头排列，MACD金叉。各模型4票看涨、1票看跌、1票震荡，综合看涨概率62%。",
  "trend": "up",
  "confidence": 62,
  "key_levels": {
    "support": [1420, 1380],
    "resistance": [1480, 1520]
  },
  "suggestion": "建议观望，等待放量突破1480确认。如放量突破可加仓，跌破1420止损。",
  "risk": "如果跌破1420支撑，可能回测1350。大盘系统性风险需关注。"
}
```

**实现文件**：`backend/app/services/predictors/llm_analyzer.py`

---

## 三、融合器设计

### 3.1 投票机制

| 模型 | 权重 | 投票方式 |
|------|------|---------|
| A. 技术指标 | 1.0 | 输出 trend + confidence 折算 |
| B. 统计模型 | 0.8 | 趋势线斜率判断方向 |
| C. 蒙特卡洛 | 0.7 | up_probability > 0.6 → 看涨 |
| D. XGBoost | 1.2 | 根据历史准确率加权 |
| E. 形态识别 | 0.9 | 最高置信度的形态方向 |
| F. 深度学习 | 1.2 | 根据历史方向准确率加权 |

**融合规则**：

```
votes = {up: 0, down: 0, sideways: 0}
weight_sum = 0

for each model:
  if model.trend == "up":
    votes.up += model.weight
  elif model.trend == "down":
    votes.down += model.weight
  else:
    votes.sideways += model.weight
  weight_sum += model.weight

ensemble_trend = max(votes)
ensemble_confidence = max(votes) / weight_sum
price_target = weighted_median(all_models' price_targets)
```

### 3.2 历史准确率追踪

每个模型维护历史预测准确率，用于动态调整权重：

```json
{
  "xgboost": {
    "predictions": 150,
    "correct": 82,
    "accuracy": 0.547,
    "last_updated": "2026-08-01"
  },
  "lstm": {
    "predictions": 120,
    "correct": 66,
    "accuracy": 0.55,
    "last_updated": "2026-08-01"
  }
}
```

**实现文件**：`backend/app/services/predictors/ensemble.py`

---

## 四、前端展示

### 4.1 K 线叠加层

```
┌──────────────────────────────────────────────────────┐
│  工具栏: [预测] [筹码] [同屏] [对比] [截图] [导出]    │
├──────────────────────────────────────────────────────┤
│  K线主图                                              │
│  ┌──────────────────────────────────────────────┐    │
│  │                                              │ R  │
│  │  ██  ██  ██  ██  ██  ██  ██  ██  ██  ██    │ 1  │
│  │  ██  ██  ██  ██  ██  ██  ██  ██  ██  ██    │ 4  │
│  │  ██  ██  ██  ██  ██  ██  ██  ██  ██  ██    │ 8  │
│  │  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘  └──┘ │ 0  │
│  │  ← 历史K线（实线） →  ← 预测K线（虚线）→    │    │
│  │                          ░░░░░░░░░░░░░░░░░░ │    │
│  │                          ░ 置信区间阴影 ░░░░ │    │
│  │                          ░░░░░░░░░░░░░░░░░░ │ S  │
│  │  ═══ 支撑位 ═══  ═══ 阻力位 ═══            │ 1  │
│  │  ▓▓▓ 双底区域 ▓▓▓                            │ 4  │
│  │  ▓▓▓ 上升旗形 ▓▓▓                            │ 2  │
│  └──────────────────────────────────────────────┘    │
│  副图: 成交量 + 预测成交量(虚线柱)                      │
└──────────────────────────────────────────────────────┘
```

### 4.2 右侧预测面板

```
┌──────────────────────────────┐
│  标注 | 复盘 | 预测 | 资料   │  ← tab 切换
├──────────────────────────────┤
│  📈 综合趋势: 看涨 62%       │
│  ━━━━━━━━━━━━━━━━━━━━━━━━  │
│  各模型投票:                  │
│  ✅ 技术指标  → 看涨 65%     │
│  ✅ 统计模型  → 看涨 55%     │
│  ✅ 蒙特卡洛  → 看涨 62%     │
│  ⚠️ XGBoost   → 震荡 52%    │
│  ✅ 形态识别  → 看涨 75%     │
│  ✅ LSTM      → 看涨 58%     │
│  ─────────────────────────  │
│  目标价: 1465 (1420~1510)    │
│  ─────────────────────────  │
│  📊 形态识别                  │
│  双底 (75%)                  │
│  上升旗形 (60%)              │
│  ─────────────────────────  │
│  📋 AI 分析                   │
│  近60日走势呈上升旗形整理...  │
│  建议: 观望, 等待突破1480    │
│  风险: 跌破1420回测1350      │
│  [刷新分析]                  │
│  ─────────────────────────  │
│  模型准确率:                  │
│  XGBoost: 54.7% (150次)     │
│  LSTM: 55.0% (120次)        │
└──────────────────────────────┘
```

### 4.3 交互

- **预测按钮**：工具栏切换预测显示/隐藏
- **预测K线**：hover 显示置信区间和模型详情
- **形态区域**：hover 显示形态名称和置信度
- **支撑/阻力**：hover 显示触碰次数
- **面板刷新**：手动刷新重新运行全部模型

---

## 五、数据需求

### 5.1 当前数据

| 指标 | 值 |
|------|-----|
| 股票数量 | 6 只 |
| 总 K 线行数 | 6,017 行 |
| 单只数据量 | ~1,000 根（2022~2026） |
| 时间跨度 | 4 年 |

### 5.2 目标数据（Phase 3 后）

| 指标 | 最低可行 | 推荐 |
|------|---------|------|
| 股票数量 | 20 只 | 50~100 只 |
| 单只数据量 | 3,000 根（10 年） | 5,000+ 根（上市以来） |
| 总 K 线行数 | 60,000 行 | 250,000+ 行 |
| 时间跨度 | 10 年 | 20+ 年 |

### 5.3 数据源

- mootdx TCP：可拉 A 股全部股票的历史日 K（2000 年至今，约 6000 根）
- 每只股票首次拉取约 3 秒（800 根/次 × 8 次分页）
- 50 只股票首次拉取约 2.5 分钟

---

## 六、文件结构

```
backend/app/services/predictors/
├── __init__.py              # 导出所有模型 + 融合器
├── technical.py             # A 方案
├── statistical.py           # B 方案
├── monte_carlo.py           # C 方案
├── xgboost_predictor.py     # D 方案
├── pattern_recognition.py   # E 方案
├── deep_learning.py         # F 方案
├── llm_analyzer.py          # G 方案
├── ensemble.py              # 融合器
├── accuracy_tracker.py      # 历史准确率追踪
└── models/                  # 训练好的模型文件
    ├── xgb_global.json
    ├── lstm_global.pt
    └── scalers/             # 归一化参数

backend/app/routers/predict.py  # 预测 API

frontend/src/
├── components/PredictPanel.vue   # 右侧预测面板
├── composables/usePredict.ts     # 预测状态管理
└── stores/predict.ts             # Pinia store
```

---

## 七、分阶段实施计划

| 阶段 | 内容 | 依赖 | 前端 | 后端 | 工时 |
|------|------|------|------|------|------|
| **P1** | A + B + C 纯数学方案 | 无 | 预测面板 + K线叠加 | 3 个 predictor | 4 天 |
| **P2** | E 形态识别 + 支撑/阻力 | 无 | 形态叠加层 | pattern_recognition | 3 天 |
| **P3** | 数据扩充 | 你加自选股 | 无 | 批量同步脚本 | 1 天 |
| **P4** | D XGBoost | P3 完成 | 模型准确率显示 | xgboost_predictor | 4 天 |
| **P5** | F LSTM/Transformer | P3 完成 | 置信度带 | deep_learning | 5 天 |
| **P6** | G LLM 分析 | 有效 API key | LLM 报告显示 | llm_analyzer | 2 天 |
| **P7** | 融合器 + 历史追踪 | P1~P6 完成 | 投票面板 | ensemble | 2 天 |

### 依赖关系图

```
P1 (A+B+C) ──→ P2 (E) ──→ P7 (融合器)
                              ↑
P3 (数据扩充) ──→ P4 (D) ────┤
                ──→ P5 (F) ────┤
                              ↑
P6 (G) ──────────────────────┘
```

### 最快上线路径

**P1 + P2 可以在本周上线**（无依赖安装，纯数学计算），提供：
- 技术指标趋势判断
- 蒙特卡洛概率区间
- 线性回归趋势线
- 形态识别 + 支撑/阻力位
- 前端 K 线叠加 + 预测面板

---

## 八、风险评估

| 风险 | 影响 | 概率 | 应对 |
|------|------|------|------|
| 预测精度低 | 用户不信任 | 高 | 显示每个模型的历史准确率，不承诺精度 |
| 数据不足 | ML/DL 模型效果差 | 中 | Phase 3 扩充数据，用 walk-forward 验证 |
| LLM API key 失效 | G 方案不可用 | 高 | 准备多个备用 key，或先用本地小模型 |
| M4 训练速度 | 用户体验差 | 低 | 异步训练 + 后台重训，不阻塞用户操作 |
| 过拟合 | 回测好看实盘差 | 高 | walk-forward 验证 + 早停 + 正则化 |
| 预测频率限制 | 用户频繁请求 | 低 | 缓存预测结果 5 分钟，每次请求间隔 > 30s |

---

## 九、验证标准

| 阶段 | 验证项 | 通过标准 |
|------|--------|---------|
| P1 | 预测 API | curl 返回 7 个字段，< 2s |
| P2 | 形态识别 | 识别出至少 1 个形态 + 支撑/阻力位 |
| P3 | 数据扩充 | 自选股 > 20 只，总 K 线 > 6 万行 |
| P4 | XGBoost 训练 | 方向准确率 > 52%（随机基线 50%） |
| P5 | LSTM 训练 | 方向准确率 > 53%，MAE < 价格 * 3% |
| P6 | LLM 分析 | 返回非空分析报告 |
| P7 | 融合器 | 6 个模型独立投票 + 加权综合 |