# GP — 自选股看盘系统

> 个人 A 股看盘 + 量化预测系统。K 线图表、画线标注、自选股管理、实时行情、6 模型融合预测、AI 分析报告。

![GitHub](https://img.shields.io/badge/stack-FastAPI_Vue3_SQLite-blue)
![GitHub](https://img.shields.io/badge/predict-6_models-orange)
![GitHub](https://img.shields.io/badge/accuracy-56.5%25-green)

---

## 快速开始

### 前置条件

- Python 3.11+
- Node.js 20+
- 一个 A 股数据源（mootdx 默认走通达信 TCP，国内网络直连可用；海外需代理）

### 安装

```bash
# 1. 克隆
git clone https://github.com/zhbcher/GP.git
cd GP

# 2. 后端
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 编辑 .env 配置密钥
cd ..

# 3. 前端
cd frontend
npm install
cd ..

# 4. 初始化数据库（自动建表，13 张表 + 19 个索引）
cd backend
python init_db.py
cd ..
```

### 启动

```bash
# 终端 1 — 后端（端口 8000）
cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2 — 前端（端口 5173，自动代理 /api 和 /ws 到后端）
cd frontend && npm run dev
```

打开 `http://localhost:5173/?key=your_auth_key`（若配置了 AUTH_KEY）或直接访问。

### 配置

复制 `.env.example` 为 `.env`，关键配置项：

| 配置 | 说明 | 默认值 |
|------|------|--------|
| `AUTH_KEY` | 访问密钥（空 = 开放） | `***` |
| `AUTH_ENABLED` | 是否启用鉴权 | `true` |
| `NEWS_AI_API_KEY` | LLM 分析报告用（OpenAI 兼容接口） | — |
| `NEWS_AI_BASE_URL` | LLM 接口地址 | `https://integrate.api.nvidia.com/v1` |
| `NEWS_AI_MODEL` | LLM 模型 | `stepfun-ai/step-3.7-flash` |

### Docker 部署

```bash
docker compose up --build -d
# 访问 http://localhost
```

---

## 功能概览

### 📊 K 线图表

- 日K/周K/月K/年K + 分时/5分/15分/30分/60分
- 前复权 / 后复权 / 不复权
- 画线工具：趋势线、水平线、射线、通道、斐波那契、矩形、箭头、文字
- 标注系统：买入/卖出/关注/复盘/其他，K 线上直接点击打标
- 筹码分布、区间统计、对比叠加

### 📋 自选股管理

- 分组管理（创建/删除/拖拽排序）
- 批量导入（代码粘贴，逗号/换行分隔）
- 条件筛选（N日涨幅、MACD金叉、RSI超买超卖、布林通道、成交量放大）
- 实时行情快照（腾讯接口，28/28 只票即时报价）

### 📈 量化预测（6 模型融合）

| 模型 | 5日方向准确率 | 融合权重 | 说明 |
|------|:---:|:---:|------|
| **XGBoost** | **56.5%** | **0.95** | 40 特征 + 全局模型 + 个股微调 |
| **LSTM** | **53.8%** | **0.68** | 60→5 滑动窗口，MPS 加速 |
| 蒙特卡洛 | 53.0% | 0.60 | bootstrap 10000 次采样 |
| 形态识别 | 50.4% | 0.34 | 双底/双顶/头肩顶/旗形/吞没 |
| 技术指标 | 49.7% | 0.10 | MA/MACD/BOLL/RSI/KDJ |
| 统计模型 | 49.5% | 0.10 | 线性回归 + 指数平滑 |

> 融合器按回测准确率自动加权，拖后腿的模型被压权。方向预测天花板约 56%，实盘数据会持续修正权重。

### 🤖 AI 分析报告

- 调用 LLM 将 6 模型结论 + K 线走势压缩为中文分析
- 包含：走势总结、操作建议、风险提示
- 按 (股票, 日期) 缓存，当天不重复调用

### 🔔 其他功能

- 持仓管理（成本/盈亏/市值）
- 价格预警（目标价/涨跌幅/放量触发）
- 交易复盘（标注回顾、复盘笔记）
- 数据备份/恢复（一键导出/导入 .db 文件）
- 定时更新（每交易日 15:30 增量拉取日K）
- 行业资讯聚合（106 个 RSS 源，中文翻译，7 天存储）

---

## 项目结构

```
GP/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 入口 + 路由注册 + 定时任务
│   │   ├── config.py           # 配置（.env）
│   │   ├── auth.py             # 鉴权中间件
│   │   ├── db.py               # 数据库引擎
│   │   ├── models/             # SQLAlchemy ORM 模型（13 张表）
│   │   ├── routers/            # API 路由（20+ 路由模块）
│   │   ├── services/           # 业务逻辑
│   │   │   ├── predictors/     # 6 个预测模型 + 融合器
│   │   │   │   ├── technical.py
│   │   │   │   ├── statistical.py
│   │   │   │   ├── monte_carlo.py
│   │   │   │   ├── pattern_recognition.py
│   │   │   │   ├── xgboost_predictor.py
│   │   │   │   ├── deep_learning.py
│   │   │   │   ├── ensemble.py
│   │   │   │   ├── llm_analyzer.py
│   │   │   │   └── models/     # 训练好的模型权重
│   │   │   ├── prediction_eval.py
│   │   │   └── prediction_store.py
│   │   └── data_sources/       # 数据源适配器
│   ├── init_db.py              # 建表脚本
│   ├── scripts/backtest.py     # walk-forward 回测框架
│   └── requirements.txt
├── frontend/                   # Vue 3 + TypeScript 前端
│   ├── src/
│   │   ├── components/         # 组件（K线图、预测面板、侧边栏等）
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── api/                # API 请求封装
│   │   └── overlays/           # K 线叠加层
│   └── package.json
├── docs/                       # 文档
│   ├── schema.sql              # 数据库表结构（13 表 + 19 索引）
│   ├── PRD.md                  # 产品需求文档
│   ├── SRS.md                  # 软件需求规格
│   ├── tech-design.md          # 技术设计文档
│   ├── backtest-report.md      # 回测分析报告
│   └── backtest-result.json    # 回测准确率数据
├── data/                       # 数据目录（gitignored）
│   └── stock.db                # SQLite 数据库
├── docker-compose.yml
├── Dockerfile
└── nginx.conf
```

---

## 技术栈

| 层 | 技术 |
|------|------|
| 前端框架 | Vue 3 + TypeScript + Vite |
| 状态管理 | Pinia |
| K 线图表 | KLineChart |
| 后端框架 | FastAPI (Python 3.11) |
| 数据库 | SQLite (aiosqlite) |
| 定时任务 | APScheduler |
| 预测模型 | XGBoost, PyTorch (LSTM), scikit-learn, statsmodels |
| 数据源 | mootdx (通达信 TCP), 腾讯行情 HTTP |
| 部署 | Docker Compose + Nginx |

---

## API 鉴权

所有 API 请求需要携带访问密钥：

```bash
# 方式 1: URL 参数
curl http://localhost:8000/api/watchlist?key=your_key

# 方式 2: Authorization 头
curl http://localhost:8000/api/watchlist -H "Authorization: Bearer your_key"
```

WebSocket 连接同样需要 `?key=your_key` 参数。

---

## 许可证

MIT