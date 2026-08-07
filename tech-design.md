# 自选股看盘系统 — 技术方案

> 版本：v1.1（多数据源优化）
> 日期：2026-07-25
> 状态：待老板确认

---

## 一、需求确认汇总

| 问题 | 老板答复 | 技术影响 |
|------|---------|---------|
| 市场 | A股 | 多数据源：mootdx + akshare + easyquotation + 腾讯财经 |
| 实时行情 | 最好有，免费 | mootdx 五档盘口（主）→ easyquotation 新浪源（备），交易时段 3s 轮询 + WebSocket 推送 |
| 部署 | 本地/云都行 | 先跑 Mac mini，Docker 化后可随时迁云 |
| 手机访问 | 需要 | KLineChart 原生支持触摸；响应式布局 |
| 数据源 | 免费 | 多源互备：mootdx/akshare/easyquotation/腾讯/百度（详见 §2.4） |
| 多设备同步 | 不需要 | 单机 SQLite，无账号系统 |
| 画线 | 股票软件标准画线 | KLineChart 内置 20+ 画线模型，全部开放 |
| 形态 | Web | Vue 3 SPA + FastAPI |

---

## 二、技术选型

### 2.1 架构图

```
┌─────────────────────────────────────────────────┐
│  浏览器（PC / 手机）                              │
│  Vue 3 + Vite + KLineChart v9 + TailwindCSS     │
│  · K线渲染 · 画线交互 · 标注交互 · 自选股列表       │
└──────────────────┬──────────────────────────────┘
                   │ REST + WebSocket
┌──────────────────▼──────────────────────────────┐
│  FastAPI (Python 3.12)                          │
│  · /api/kline     历史K线（日/周/月/年，复权）     │
│  · /api/stock     搜索 / 自选股 CRUD             │
│  · /api/drawing   画线 CRUD                     │
│  · /api/annotation 标注 CRUD + 导出              │
│  · /ws/quote      实时行情 WebSocket 推送         │
│  · 定时任务：收盘后增量更新（APScheduler）          │
├─────────────────────────────────────────────────┤
│  数据源抽象层（DataSourceManager）                │
│  优先级路由 + 自动降级 + 本地缓存兜底              │
│  ┌───────────┬───────────┬───────────┐          │
│  │ 历史K线    │ 实时行情   │ 复权/列表  │          │
│  │ ①mootdx   │ ①mootdx   │ ①akshare  │          │
│  │ ②akshare  │ ②easyquot │ ②mootdx   │          │
│  │ ③百度K线  │ ③腾讯财经  │           │          │
│  └───────────┴───────────┴───────────┘          │
│  参考：a-stock-data SKILL.md（15源直连模式）       │
├─────────────────────────────────────────────────┤
│  存储层                                          │
│  SQLite（watchlist / kline / drawings /          │
│          annotations / adjust_factor）           │
└─────────────────────────────────────────────────┘
```

### 2.2 选型理由

| 组件 | 选择 | 为什么 | 备选（弃用原因） |
|------|------|--------|----------------|
| K线图表 | **KLineChart v9** ⭐3988 | 零依赖 40k gzip；内置画线模型 20+（趋势线/水平线/射线/平行线/斐波那契/矩形/箭头/文字）；内置指标 MA/MACD/KDJ/BOLL；原生移动端触摸；TypeScript；Apache-2.0 | Lightweight Charts（画线需自己实现，工作量大 3 倍）；ECharts（K线交互弱，画线不支持） |
| 前端框架 | **Vue 3 + Vite** | 轻量、生态成熟、KLineChart 官方有 Vue 集成示例 | React（可以但无优势）；原生 JS（状态管理痛苦） |
| 后端 | **FastAPI** | mootdx/akshare/easyquotation 都是 Python 库，同语言零胶水；原生 WebSocket；异步性能好 | Node.js（调 Python 数据源要起子进程，多一层） |
| 数据库 | **SQLite** | 单机个人用，零运维；WAL 模式读写并发够用；一个文件备份 | PostgreSQL（杀鸡用牛刀） |
| 历史K线 | **mootdx**（主）+ **akshare**（备） | mootdx 走通达信 TCP 7709，**不封 IP**，K线/五档/逐笔；akshare 补复权因子 + 股票列表 | 单用 akshare（走东财 HTTP 有风控封 IP 风险） |
| 实时行情 | **mootdx 五档**（主）+ **easyquotation**（备） | mootdx TCP 实时报价 46 字段；easyquotation 新浪源兜底 | 单用 easyquotation（新浪源偶尔不稳定） |
| 估值数据 | **腾讯财经** | PE/PB/市值/换手率/涨跌停价，不封 IP | 东财（有风控） |
| 部署 | **Docker Compose** | Mac mini 先跑，随时可迁云；一条命令启动 | 直接跑（依赖管理麻烦） |

### 2.3 参考项目

| 项目 | Stars | 参考价值 |
|------|-------|---------|
| klinecharts/KLineChart | 3988 | 核心图表库，画线 API 文档完善 |
| klinecharts/samples | 194 | 官方示例，画线/指标用法参考 |
| klinecharts/pro | — | 官方金融图表产品，布局参考 |
| **simonlin1212/a-stock-data** | — | **多数据源架构参考**：15 源直连、优先级路由、降级策略、em_get() 限流模式；mootdx tdx_client() 用法 |
| lc2panda/StockAnal_Sys | 868 | Flask + akshare 数据层写法参考 |
| wzy0x/crypto-replay | 3 | Vue 3 + KLineCharts 复盘系统，标注交互参考 |

### 2.4 多数据源架构（v1.1 新增）

#### 数据源优先级

| 优先级 | 数据源 | 协议 | 封IP风险 | 用途 |
|--------|--------|------|---------|------|
| 1（首选） | **mootdx（通达信）** | TCP 7709 | **不封** | K线(日/周/月)、五档盘口、实时报价、逐笔成交 |
| 2 | **akshare** | HTTP（东财/新浪等） | 中（东财有风控） | 复权因子、股票列表搜索、历史K线备份 |
| 3 | **easyquotation** | HTTP（新浪） | 低 | 实时行情备份（全市场快照） |
| 4 | **腾讯财经** | HTTP | **不封** | PE/PB/市值/换手率/涨跌停价 |
| 5 | **百度股市通** | HTTP | 极低 | 日K线备份（带 MA5/10/20） |

#### 各数据类型路由

| 数据类型 | 主源 | 备源 | 说明 |
|---------|------|------|------|
| 历史日K | mootdx `bars()` | akshare `stock_zh_a_hist()` | mootdx 返回不复权原始价 |
| 周K/月K | 后端从日K聚合 | mootdx `bars(frequency=周/月)` | 聚合为主，mootdx 直取为验 |
| 复权因子 | akshare `stock_zh_a_hist()` adjust 参数 | 本地计算（分红送转推算） | mootdx 不提供复权因子 |
| 实时报价 | mootdx `quotes()` | easyquotation `get_realtime_quotes()` | mootdx 46 字段含五档 |
| 股票搜索 | akshare `stock_info_a_code_name()` | mootdx 代码列表 | 含拼音首字母索引 |
| PE/PB/市值 | 腾讯财经 `qt.gtimg.cn` | akshare | 不封 IP，稳定 |

#### DataSourceManager 设计

```python
class DataSourceManager:
    """多源数据管理器：优先级路由 + 自动降级 + 缓存兜底"""

    async def get_kline(self, code, period, adjust) -> list[dict]:
        # 1. 查本地 SQLite 缓存（命中且非当日 → 直接返回）
        # 2. 缓存未命中 → 按优先级尝试数据源
        for source in [mootdx_source, akshare_source, baidu_source]:
            try:
                data = await source.fetch_kline(code, period)
                self._update_cache(code, period, data)
                return data
            except DataSourceError as e:
                logger.warning(f"{source.name} failed: {e}, trying next")
        # 3. 全部失败 → 返回过期缓存 + 标记 stale
        return self._get_stale_cache(code, period)

    async def get_realtime(self, codes: list[str]) -> dict:
        # mootdx 批量报价（TCP，快）→ easyquotation（HTTP，兜底）
        ...
```

#### 关键注意事项（来自 a-stock-data 实战经验）

1. **mootdx 0.11.x BESTIP bug**：全新安装 BESTIP 空串崩溃，需 `tdx_client()` helper（TCP 探测可用服务器 + 三级 fallback），参考 a-stock-data 实现
2. **mootdx 返回不复权**：跨除权日须自行复权，复权因子从 akshare 获取
3. **akshare 东财接口风控**：批量拉取时间隔 ≥1s，避免 IP 被封；个人使用频率低，风险可控
4. **mootdx 需国内 IP**：Mac mini 在国内没问题；若迁海外服务器需代理或切 akshare
5. **httpx 版本冲突**：mootdx 锁 httpx<0.26，FastAPI 需 httpx≥0.27 → 用 `--no-deps` 绕过（mootdx 走 TCP 不用 httpx）

---

## 三、关键设计决策

### 3.1 画线锚定（F-17 核心难点）

KLineChart 的 overlay 支持 `points: [{ timestamp, value }]` 绑定到数据点。
- 画线时：记录 `{ timestamp: K线时间戳, value: 价格 }`
- 缩放/平移/切换周期：overlay 自动跟随数据点重绘
- 持久化：points JSON 存 SQLite，加载时 `createOverlay({ points })` 恢复
- **周K/月K 切换时**：timestamp 对齐到对应周期的 K 线起点（向下取整）

### 3.2 标注系统（KLineChart 无内置，需自定义）

- 用 KLineChart 的 **自定义 overlay** 机制注册 `stockAnnotation` overlay 类型
- 点击 K 线 → 获取 `timestamp + price` → 弹出标注编辑框
- 渲染：Excel 批注风格，在 K 线角落画一个**彩色小圆点**，颜色按标注类型区分
- hover：圆点上显示 tooltip（类型色块 + 日期 + 内容文字）
- 点击圆点 → 打开编辑（修改/删除）
- 副图联动：标注列表点击 → 主图滚动定位到对应 K 线

#### Excel 批注渲染方案

```
KLineChart overlay renderResult（createPointFigures 返回）：

    ●  ← 彩色圆点（K线左上角/右上角，颜色 = 类型色）
   /│\
  / │ \
 │  │  │  ← K线柱体
  \ │ /
   \│/
    │

createPointFigures 返回两个 figure：
  1. 圆点：type='circle'，位置偏移到 K 线角落（above→右上角，below→左下角）
  2. 不画其他内容——tooltip 用 DOM overlay 实现，排版更好
```

实际 render 方案：用 KLineChart 的 `circle` figure type 画圆点，hover tooltip 用 DOM 元素（绝对定位在图表容器内），不受 Canvas 渲染限制。

**为什么不用 icon_font：** Excel 批注不需要图标，彩色圆点 + tooltip 更简洁，用户认知成本为零。

#### 标注数量与显示策略

- 单只股票预期 ~50 个标注，平均每天一根K线最多1-2个，**不需要密集防重叠**
- 同屏可见K线内如果标注超过 8 个，缩小圆点半径（10px → 6px）
- 缩放级别极小时（可见K线 > 200根），仅显示圆点，不显示 tooltip

#### 显示过滤

- 工具栏提供 5 个类型开关（买入/卖出/关注/复盘/其他），每个可独立切换显示/隐藏
- 通过 `chart.overrideOverlay({ id, visible })` 批量控制
- 默认全部显示

### 3.3 实时行情方案（多源）

```
交易时段（9:15-15:05，周一至周五）：
  后端 APScheduler 每 3s：
    ① mootdx quotes(自选股列表)  ← TCP 直连，快，含五档
    ② 失败 → easyquotation.get_realtime_quotes()  ← 新浪 HTTP 兜底
  → WebSocket 广播 { code, price, change_pct, volume, bid/ask }
  → 前端更新自选股列表价格 + 当前股票最新K线点

非交易时段：不轮询，显示收盘数据
```

mootdx 实时报价 46 字段，比 easyquotation 多了五档盘口和涨跌停价，前端可选展示。

### 3.4 数据更新策略（多源）

| 场景 | 策略 |
|------|------|
| 首次添加自选股 | ① mootdx `bars()` 拉上市以来日K（不复权）→ ② akshare 拉复权因子 → 合并存 SQLite |
| 每日收盘后 | APScheduler 15:30 触发：mootdx 增量拉当日K线 + akshare 更新复权因子 |
| 周K/月K/年K | **后端聚合**：从日K数据聚合生成，不单独存储；mootdx 直取周/月K 做交叉验证 |
| 复权 | 存不复权原始数据 + 复权因子表（akshare），前端切换时后端计算复权价 |
| 数据源全挂 | 返回本地缓存（标记 stale），下次启动自动补拉 |

### 3.5 移动端适配

- KLineChart 原生支持触摸（单指拖拽、双指缩放）
- 响应式布局：手机端自选股列表收为底部抽屉
- 画线工具栏：手机端改为底部横向滚动工具条
- 标注输入：弹出全屏编辑面板（手机键盘友好）

---

## 四、API 设计（概要）

```
GET  /api/stock/search?q=茅台          # 搜索（代码/名称/拼音）
GET  /api/stock/{code}/kline?period=daily&adjust=qfq&limit=2500
POST /api/watchlist                     # 添加自选
GET  /api/watchlist                     # 自选列表（含分组）
PUT  /api/watchlist/{id}                # 更新（备注/分组/排序）
DELETE /api/watchlist/{id}
POST /api/watchlist/groups              # 创建分组
GET  /api/drawings?stock_code=sh600519
POST /api/drawings                      # 保存画线
PUT  /api/drawings/{id}
DELETE /api/drawings/{id}
GET  /api/annotations?stock_code=sh600519
POST /api/annotations                   # 创建标注
PUT  /api/annotations/{id}
DELETE /api/annotations/{id}
GET  /api/annotations/export?stock_code=sh600519&format=md
WS   /ws/quote                          # 实时行情推送
```

---

## 五、项目结构

```
stock-watchlist/
├── frontend/                  # Vue 3 + Vite
│   ├── src/
│   │   ├── components/
│   │   │   ├── KlineChart.vue        # K线主图（KLineChart 封装）
│   │   │   ├── DrawingToolbar.vue    # 画线工具栏
│   │   │   ├── WatchlistSidebar.vue  # 自选股列表
│   │   │   ├── AnnotationPanel.vue   # 标注列表/编辑
│   │   │   └── StockSearch.vue       # 搜索框
│   │   ├── overlays/
│   │   │   └── annotationOverlay.ts   # 标注 overlay 注册 + tooltip 管理
│   │   ├── stores/                   # Pinia 状态
│   │   └── api/                      # API 封装
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI 入口
│   │   ├── routers/                  # stock / watchlist / drawing / annotation / ws
│   │   ├── data_sources/             # 多数据源抽象层
│   │   │   ├── manager.py            # DataSourceManager（优先级路由+降级）
│   │   │   ├── mootdx_source.py      # 通达信 TCP（K线/实时/五档）
│   │   │   ├── akshare_source.py     # akshare（复权因子/股票列表/K线备份）
│   │   │   ├── easyquotation_source.py # 新浪实时行情（备份）
│   │   │   ├── tencent_source.py     # 腾讯财经（PE/PB/市值）
│   │   │   └── baidu_source.py       # 百度K线（备份）
│   │   ├── services/
│   │   │   ├── kline_service.py      # K线业务逻辑（复权计算/聚合）
│   │   │   ├── realtime.py           # 实时行情服务（多源切换）
│   │   │   └── stock_search.py       # 股票搜索（代码/名称/拼音）
│   │   ├── models.py                 # SQLAlchemy 模型
│   │   └── scheduler.py              # APScheduler 定时任务
│   └── requirements.txt              # mootdx akshare easyquotation fastapi sqlalchemy apscheduler
├── data/
│   └── stock.db                      # SQLite
├── docker-compose.yml
└── Makefile                          # make dev / make prod
```

---

## 六、风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| mootdx 库烂尾（最后 commit 2024-07） | 未来可能装不上 | tdx_client() 绕开 BESTIP bug；社区替代 easy_tdx 同协议；akshare 随时可顶上 |
| akshare 东财接口风控封 IP | 复权因子/列表拉取失败 | 个人使用频率低；间隔 ≥1s；mootdx 不依赖东财 |
| 全部数据源同时挂 | 无新数据 | 本地 SQLite 缓存兜底（标记 stale），恢复后自动补拉 |
| mootdx 需国内 IP | 迁海外服务器不可用 | 切 akshare 为主源（改 manager.py 优先级即可） |
| httpx 版本冲突（mootdx <0.26 vs FastAPI ≥0.27） | 安装报错 | `pip install --no-deps "httpx>=0.27.1"` 绕过（mootdx 走 TCP 不用 httpx） |
| 10 年数据量大（~2500 根日K） | 首次加载慢 | SQLite 索引 + 分页加载（KLineChart 支持增量加载）；周K/月K 数据量小 |
| 画线跨周期对齐 | 日K 画的线在周K 位置偏移 | timestamp 向下取整到周期起点；画线绑定具体周期 |
| 手机画线操作精度 | 触摸点不准 | KLineChart 支持磁吸模式（自动吸附最近 K 线点） |
