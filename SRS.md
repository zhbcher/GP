# 自选股看盘系统 — 软件需求规格说明书（SRS）

> 版本：v1.0
> 日期：2026-07-25
> 作者：旺财
> 状态：待老板确认
> 关联文档：[PRD](./PRD.md) · [技术方案](./tech-design.md) · [需求初稿](./requirements.md)

---

## 1. 引言

### 1.1 目的

本文档定义自选股看盘系统的完整软件需求规格，作为设计、开发、测试和验收的依据。

### 1.2 范围

- **系统名称：** 自选股看盘系统（stock-watchlist）
- **形态：** Web 应用（前后端分离），PC + 手机浏览器访问
- **用户：** 单人（老板），无账号体系
- **市场：** A 股（沪深）
- **部署：** 本地 Mac mini（Docker），可迁云

### 1.3 术语

| 术语 | 定义 |
|------|------|
| K 线 | 蜡烛图，含 OHLCV（开高低收量） |
| 复权 | 前复权(qfq)/后复权(hfq)/不复权(none)，消除除权除息跳空 |
| 画线 | 在 K 线图上绘制的分析线条（趋势线、水平线等） |
| 标注 | 在特定 K 线上打的文字笔记（买入/卖出/关注/复盘） |
| 周期 | 日K/周K/月K/年K |
| 磁吸 | 画线时自动吸附最近 K 线数据点 |
| 主源/备源 | 多数据源架构中的优先级路由 |

---

## 2. 系统架构

### 2.1 总体架构

```
┌─────────────────────────────────────────────────┐
│  浏览器（PC / 手机）                              │
│  Vue 3 + Vite + KLineChart v9 + TailwindCSS     │
│  Pinia 状态管理 · WebSocket 客户端               │
└──────────────────┬──────────────────────────────┘
                   │ REST (JSON) + WebSocket
┌──────────────────▼──────────────────────────────┐
│  FastAPI (Python 3.12, uvicorn)                 │
│  路由层 → 业务层 → 数据源抽象层 → 存储层          │
├─────────────────────────────────────────────────┤
│  DataSourceManager（多源优先级路由 + 自动降级）    │
│  mootdx(TCP) → akshare(HTTP) → easyquotation    │
│  → 腾讯财经(HTTP) → 百度K线(HTTP)               │
├─────────────────────────────────────────────────┤
│  SQLite (WAL 模式)                              │
│  kline_data · adjust_factor · watchlist ·       │
│  groups · drawings · annotations                │
└─────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层 | 技术 | 版本 |
|----|------|------|
| 前端框架 | Vue 3 + Vite | Vue 3.5+, Vite 6+ |
| K 线图表 | KLineChart | v9.x |
| CSS | TailwindCSS | v4+ |
| 状态管理 | Pinia | v2+ |
| 后端框架 | FastAPI + uvicorn | FastAPI 0.115+ |
| ORM | SQLAlchemy (async) + aiosqlite | 2.0+ |
| 数据源 | mootdx + akshare + easyquotation | 最新稳定版 |
| 定时任务 | APScheduler | 3.x |
| 部署 | Docker Compose | — |

---

## 3. 数据模型

### 3.1 ER 关系

```
groups 1──N watchlist 1──N drawings
                      1──N annotations
                      1──N kline_data
                      1──N adjust_factor
```

### 3.2 表结构

#### groups（分组）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | |
| name | TEXT | NOT NULL, UNIQUE | 分组名（重仓/观察/已清仓） |
| sort_order | INTEGER | DEFAULT 0 | 排序权重 |
| created_at | DATETIME | DEFAULT NOW | |

#### watchlist（自选股）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | TEXT | NOT NULL, UNIQUE | 如 sh600519, sz000858 |
| stock_name | TEXT | NOT NULL | 如 贵州茅台 |
| group_id | INTEGER | FK → groups.id, NULLABLE | 所属分组，NULL=默认组 |
| note | TEXT | DEFAULT '' | 备注（关注理由） |
| sort_order | INTEGER | DEFAULT 0 | 排序权重 |
| created_at | DATETIME | DEFAULT NOW | |

#### kline_data（K 线数据）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | TEXT | NOT NULL | |
| trade_date | DATE | NOT NULL | 交易日期 |
| open | REAL | NOT NULL | 开盘价（不复权） |
| high | REAL | NOT NULL | 最高价 |
| low | REAL | NOT NULL | 最低价 |
| close | REAL | NOT NULL | 收盘价 |
| volume | INTEGER | NOT NULL | 成交量（手） |
| amount | REAL | DEFAULT 0 | 成交额（元） |
| | | UNIQUE(stock_code, trade_date) | |

> 索引：`idx_kline_code_date (stock_code, trade_date)`
> 只存日 K 不复权原始数据。周/月/年 K 由后端聚合。

#### adjust_factor（复权因子）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | TEXT | NOT NULL | |
| trade_date | DATE | NOT NULL | |
| factor | REAL | NOT NULL | 复权因子（akshare 提供） |
| | | UNIQUE(stock_code, trade_date) | |

#### drawings（画线）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | TEXT | NOT NULL | |
| period | TEXT | NOT NULL, DEFAULT 'daily' | 画线所在周期 |
| type | TEXT | NOT NULL | trendline/horizontal/ray/channel/fib/rect/arrow/text |
| points | TEXT (JSON) | NOT NULL | `[{"timestamp":1700000000,"value":1800.5}, ...]` |
| style | TEXT (JSON) | DEFAULT '{}' | `{"color":"#ff0000","lineWidth":2,"dashed":false}` |
| text_content | TEXT | NULLABLE | type=text 时的文字内容 |
| visible | INTEGER | DEFAULT 1 | 是否显示 |
| created_at | DATETIME | DEFAULT NOW | |
| updated_at | DATETIME | DEFAULT NOW | |

> 索引：`idx_drawing_code (stock_code, period)`

#### annotations（标注）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK | |
| stock_code | TEXT | NOT NULL | |
| trade_date | DATE | NOT NULL | 标注所在 K 线日期 |
| type | TEXT | NOT NULL, DEFAULT 'watch' | buy/sell/watch/review/other |
| content | TEXT | NOT NULL | 标注文字 |
| position | TEXT | DEFAULT 'above' | above/below（K 线上方/下方） |
| created_at | DATETIME | DEFAULT NOW | |
| updated_at | DATETIME | DEFAULT NOW | |

> 索引：`idx_annotation_code_date (stock_code, trade_date)`

### 3.3 标注类型颜色映射

| type | 显示名 | 颜色 | 图标 |
|------|--------|------|------|
| buy | 买入 | #22c55e (绿) | ▲ |
| sell | 卖出 | #ef4444 (红) | ▼ |
| watch | 关注 | #eab308 (黄) | ● |
| review | 复盘 | #3b82f6 (蓝) | ◆ |
| other | 其他 | #9ca3af (灰) | ○ |

---

## 4. API 规格

> 基础路径：`/api`
> 格式：JSON，UTF-8
> 错误格式：`{"detail": "错误描述"}`

### 4.1 股票搜索

```
GET /api/stock/search?q={keyword}&limit=20
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| q | string | 是 | 代码/名称/拼音首字母 |
| limit | int | 否 | 返回条数，默认 20 |

**响应 200：**
```json
[
  {"code": "sh600519", "name": "贵州茅台", "pinyin": "gzmt"},
  {"code": "sz000858", "name": "五粮液", "pinyin": "wly"}
]
```

### 4.2 K 线数据

```
GET /api/stock/{code}/kline?period={period}&adjust={adjust}&limit={limit}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 路径参数，如 sh600519 |
| period | string | 否 | daily(默认)/weekly/monthly/yearly |
| adjust | string | 否 | qfq(默认)/hfq/none |
| limit | int | 否 | 返回条数，默认 2500 |

**响应 200：**
```json
{
  "code": "sh600519",
  "name": "贵州茅台",
  "period": "daily",
  "adjust": "qfq",
  "data": [
    {"timestamp": 1700000000000, "open": 1800.0, "high": 1820.5, "low": 1795.0, "close": 1815.0, "volume": 25000, "turnover": 4537500000}
  ],
  "count": 2500
}
```

> timestamp 为毫秒级 Unix 时间戳（KLineChart 要求）。
> 周/月/年 K 由后端从日 K 聚合：open=首根 open, high=max(high), low=min(low), close=末根 close, volume=sum。

### 4.3 自选股 CRUD

```
GET    /api/watchlist                          # 列表（含分组、实时价）
POST   /api/watchlist                          # 添加
PUT    /api/watchlist/{id}                     # 更新（备注/分组/排序）
DELETE /api/watchlist/{id}                     # 删除（保留标注/画线）
```

**POST 请求体：**
```json
{"stock_code": "sh600519", "group_id": 1, "note": "白酒龙头，估值合理区间"}
```

**GET 响应：**
```json
{
  "groups": [
    {"id": 1, "name": "重仓", "stocks": [
      {"id": 1, "stock_code": "sh600519", "stock_name": "贵州茅台", "note": "...", "sort_order": 0,
       "realtime": {"price": 1815.0, "change_pct": 1.25, "volume": 25000}}
    ]}
  ],
  "ungrouped": []
}
```

### 4.4 分组 CRUD

```
GET    /api/watchlist/groups
POST   /api/watchlist/groups                   # {"name": "观察"}
PUT    /api/watchlist/groups/{id}              # {"name": "新名称", "sort_order": 1}
DELETE /api/watchlist/groups/{id}              # 组内股票移到默认组
```

### 4.5 画线 CRUD

```
GET    /api/drawings?stock_code={code}&period={period}
POST   /api/drawings
PUT    /api/drawings/{id}
DELETE /api/drawings/{id}
```

**POST 请求体：**
```json
{
  "stock_code": "sh600519",
  "period": "daily",
  "type": "trendline",
  "points": [{"timestamp": 1700000000000, "value": 1750.0}, {"timestamp": 1710000000000, "value": 1850.0}],
  "style": {"color": "#ff0000", "lineWidth": 2, "dashed": false}
}
```

### 4.6 标注 CRUD

```
GET    /api/annotations?stock_code={code}
POST   /api/annotations
PUT    /api/annotations/{id}
DELETE /api/annotations/{id}
DELETE /api/annotations?stock_code={code}          # 批量删除（删除该股全部标注）
PATCH  /api/annotations/display                    # 批量切换显示/隐藏
```

**POST 请求体：**
```json
{
  "stock_code": "sh600519",
  "trade_date": "2024-09-30",
  "type": "buy",
  "content": "估值回到合理区间，分批建仓",
  "position": "below"
}
```

**批量删除：**
```
DELETE /api/annotations?stock_code=sh600519
```
删除该股票的全部标注，不可恢复。返回 `{"deleted": 42}`。

**显示切换：**
```json
// PATCH /api/annotations/display
{
  "stock_code": "sh600519",
  "type": "buy",           // 按类型切换；不传 type 则切换全部
  "visible": false         // true=显示, false=隐藏
}
```
返回该操作后的可见标注数量。前端根据返回结果调用 `chart.overrideOverlay({ visible })`。

### 4.7 标注导出

```
GET /api/annotations/export?stock_code={code}&format={format}
```

| 参数 | 说明 |
|------|------|
| format | md（默认）/ csv |

**Markdown 导出格式：**
```markdown
# 贵州茅台 (sh600519) 交易标注

| 日期 | 类型 | 内容 | 当日收盘 | 当日涨跌 |
|------|------|------|---------|---------|
| 2024-09-30 | 买入 | 估值回到合理区间 | 1815.00 | +1.25% |
```

### 4.8 实时行情 WebSocket

```
WS /ws/quote
```

**服务端推送（每 3s，交易时段）：**
```json
{
  "type": "quote_update",
  "data": {
    "sh600519": {"price": 1815.0, "change_pct": 1.25, "volume": 25000, "high": 1820.5, "low": 1795.0, "open": 1800.0},
    "sz000858": {"price": 155.3, "change_pct": -0.45, "volume": 180000}
  },
  "timestamp": 1700000000000
}
```

**客户端 → 服务端（订阅）：**
```json
{"type": "subscribe", "codes": ["sh600519", "sz000858"]}
```

**非交易时段：** 连接保持但不推送，前端显示收盘数据。

### 4.9 健康检查

```
GET /api/health → {"status": "ok", "version": "1.0.0", "data_sources": {"mootdx": "connected", "akshare": "ok"}}
```

---

## 5. 数据源规格

### 5.1 优先级路由

| 数据类型 | 主源 | 备源 1 | 备源 2 |
|---------|------|--------|--------|
| 历史日 K | mootdx `bars()` | akshare `stock_zh_a_hist()` | 百度 K 线 |
| 复权因子 | akshare | — | 本地推算（分红送转） |
| 实时报价 | mootdx `quotes()` | easyquotation | 腾讯财经 |
| 股票搜索 | akshare `stock_info_a_code_name()` | mootdx 代码列表 | — |
| PE/PB/市值 | 腾讯财经 | akshare | — |

### 5.2 降级规则

```
DataSourceManager.fetch():
  1. 查本地 SQLite 缓存
     命中且非当日数据 → 直接返回
  2. 缓存未命中 → 按优先级依次尝试数据源
     成功 → 写入缓存 → 返回
     失败 → 记录日志 → 尝试下一源
  3. 全部失败 → 返回过期缓存（标记 stale=true）
  4. 无缓存且全部失败 → 返回 503 + 错误信息
```

### 5.3 数据源约束

| 数据源 | 协议 | 限流 | 注意事项 |
|--------|------|------|---------|
| mootdx | TCP 7709 | 无 | 需国内 IP；0.11.x BESTIP bug 需 tdx_client() 绕过；返回不复权数据 |
| akshare | HTTP | 东财接口间隔 ≥1s | 批量拉取需节流；pandas 版本兼容 |
| easyquotation | HTTP（新浪） | 无明确限制 | 偶尔超时，3s 超时降级 |
| 腾讯财经 | HTTP | 无 | 字段编号有坑（43=振幅非PB，46=PB） |
| 百度 K 线 | HTTP | 极低 | 仅日 K，带 MA 均价 |

### 5.4 定时任务

| 任务 | 触发时间 | 逻辑 |
|------|---------|------|
| 日 K 增量更新 | 每交易日 15:30 | 遍历自选股，mootdx 拉当日 K 线，akshare 更新复权因子 |
| 数据完整性检查 | 每日 16:00 | 检查近 5 交易日数据完整性，缺失则补拉 |
| 实时行情轮询 | 交易时段 9:15-15:05 | 每 3s mootdx quotes → WebSocket 广播 |

> 交易时段判断：周一至周五，排除法定节假日（本地维护节假日表或调 akshare 交易日历）。

---

## 6. 前端规格

### 6.1 组件树

```
App.vue
├── TopBar.vue                    # 搜索框 + 股票信息 + 周期/复权/指标切换
├── WatchlistSidebar.vue          # 自选股列表（PC 侧边栏 / 手机底部抽屉）
│   ├── GroupTabs.vue
│   └── StockItem.vue             # 单只股票（代码/名称/实时价/涨跌幅）
├── KlineChartWrapper.vue         # KLineChart 封装
│   ├── overlays/annotation.ts    # 自定义标注 overlay
│   └── overlays/magnet.ts        # 磁吸辅助
├── DrawingToolbar.vue            # 画线工具栏
├── AnnotationPanel.vue           # 标注列表 + 编辑
├── AnnotationEditor.vue          # 标注编辑弹框
└── StockSearch.vue               # 搜索下拉
```

### 6.2 KLineChart 配置要点

| 配置项 | 值 | 说明 |
|--------|-----|------|
| 主图指标 | MA(5,10,20,60,120,250) | 可开关 |
| 副图 | 成交量（默认）+ MACD/KDJ/BOLL 可切换 | |
| 画线模型 | straightLine, horizontalLine, ray, parallelLine, fibonacciLine, rect, arrow, simpleAnnotation(自定义) | |
| 磁吸模式 | `createOverlay({ mode: 'magnet' })` | 画线时吸附 K 线点 |
| 数据格式 | `{ timestamp, open, high, low, close, volume }` | timestamp 毫秒 |
| 增量加载 | `chart.loadMore()` | 首屏 500 根，左滑加载更多 |
| 移动端 | 单指拖拽、双指缩放 | KLineChart 原生支持 |

### 6.3 标注 Overlay 规格

Excel 批注风格：K 线角落彩色小圆点 + hover tooltip。

#### Overlay 注册

```typescript
chart.registerOverlay<AnnotationExtendData>({
  name: 'stockAnnotation',
  totalStep: 1,                        // 一步：点击K线即创建
  needDefaultPointFigure: false,       // 自己画圆点，不要默认样式
  drawingMode: 'step',
  mode: 'weak_magnet',
  modeSensitivity: 5,
  lock: false,

  createPointFigures: ({ coordinates, overlay }) => {
    const ext = overlay.extendData as AnnotationExtendData;
    const isAbove = ext.position === 'above';

    return [{
      type: 'circle',
      attrs: {
        cx: isAbove ? 6 : -6,         // 圆点X偏移（above→左，below→右）
        cy: isAbove ? -10 : 10,       // 圆点Y偏移（above→上，below→下）
        r: 7,                          // 半径7px
      },
      styles: {
        color: ANNOTATION_COLORS[ext.type],
        borderColor: '#ffffff',
        borderSize: 2,
      },
    }];
  },

  onMouseEnter: (event) => {
    const ext = event.overlay.extendData as AnnotationExtendData;
    const point = event.overlay.points[0];
    const pixel = event.chart.convertToPixel({
      timestamp: point.timestamp!,
      value: point.value!,
    });
    showTooltip(pixel, ext);           // 显示 DOM tooltip
  },

  onMouseLeave: () => {
    hideTooltip();
  },

  onClick: (event) => {
    openEditor(event.overlay.extendData.annotationId);
  },
});
```

#### Tooltip 渲染（DOM 实现）

```html
<div class="annotation-tooltip" :style="{ left, top }">
  <div class="tooltip-header">
    <span class="tooltip-dot" :style="{ background: typeColor }"></span>
    <span class="tooltip-type">{{ typeLabel }}</span>
    <span class="tooltip-date">{{ date }}</span>
  </div>
  <div class="tooltip-content">{{ content }}</div>
</div>
```

| 属性 | 值 |
|------|-----|
| 圆点颜色 | 按类型：#22c55e(买入) / #ef4444(卖出) / #eab308(关注) / #3b82f6(复盘) / #9ca3af(其他) |
| 圆点尺寸 | 7px 半径，白色描边 2px |
| tooltip 位置 | 圆点上方，边界自动翻转 |
| tooltip 内容 | 类型色块 + 日期 + 内容文字 |
| 触发方式 | hover（PC）/ 单击（移动端，无 hover） |

#### 标注类型颜色映射

| type | 显示名 | 颜色 | 用途 |
|------|--------|------|------|
| buy | 买入 | #22c55e | 记录买入决策 |
| sell | 卖出 | #ef4444 | 记录卖出决策 |
| watch | 关注 | #eab308 | 关注信号/潜在机会 |
| review | 复盘 | #3b82f6 | 事后复盘笔记 |
| other | 其他 | #9ca3af | 其他备注 |

#### 交互流程

1. 用户点击工具栏"标注"按钮 → 进入放置模式（光标变十字）
2. 单击某根 K 线 → 弹出 AnnotationEditor（类型选择 + 文字输入）
3. 保存 → POST /api/annotations → 创建 overlay 实例（彩色圆点）
4. hover 圆点 → DOM tooltip 显示（类型 + 日期 + 内容）
5. 单击圆点 → 打开编辑面板（修改/删除）

#### 状态机

| 状态 | 触发 | 下一状态 |
|------|------|----------|
| idle | 点击"标注"按钮 | placing |
| placing | 点击K线 | editing（弹出编辑器） |
| placing | Esc / 取消按钮 | idle |
| editing | 保存 | idle |
| editing | 取消/删除 | idle |

#### 显示控制

- 工具栏提供 5 个类型开关，独立控制每种标注的可见性
- 调用 `chart.overrideOverlay({ visible: true/false })` 批量切换
- 支持"显示全部"/"隐藏全部"快捷操作

### 6.4 状态管理（Pinia）

```
stores/
├── stock.ts        # 当前股票（code/name/period/adjust）
├── kline.ts        # K线数据 + 加载状态
├── watchlist.ts    # 自选股列表 + 分组
├── drawing.ts      # 画线列表 + 当前工具
├── annotation.ts   # 标注列表 + 编辑状态
└── realtime.ts     # WebSocket 连接 + 实时价格
```

### 6.5 响应式断点

| 断点 | 布局 |
|------|------|
| ≥ 1024px (PC) | 侧边栏 280px + K线区自适应 |
| < 1024px (手机) | K线全屏，自选股底部抽屉，工具栏底部滚动 |

---

## 7. 错误处理

### 7.1 后端错误码

| HTTP 状态 | 场景 | 响应体 |
|-----------|------|--------|
| 400 | 参数校验失败 | `{"detail": "period must be daily/weekly/monthly/yearly"}` |
| 404 | 股票不存在 / 资源不存在 | `{"detail": "stock sh999999 not found"}` |
| 409 | 重复添加自选 | `{"detail": "sh600519 already in watchlist"}` |
| 503 | 全部数据源不可用 | `{"detail": "all data sources unavailable", "stale_data": true}` |

### 7.2 前端错误处理

| 场景 | 处理 |
|------|------|
| K 线加载失败 | Toast 提示 + 显示本地缓存（标记"数据可能过期"） |
| WebSocket 断连 | 自动重连（指数退避 1s→2s→4s→8s→30s），重连期间显示最后价格 |
| 画线保存失败 | 本地暂存，恢复后重试 |
| 搜索无结果 | 显示"未找到匹配股票" |

---

## 8. 性能指标

| 指标 | 目标 | 测量方法 |
|------|------|---------|
| 日 K 2500 根渲染 | 首屏 < 1s，缩放拖拽 ≥ 30fps | Chrome DevTools Performance |
| 切换股票 | < 1s（本地缓存命中） | 从点击到 K 线渲染完成 |
| 搜索响应 | < 500ms | 输入到下拉列表出现 |
| 画线恢复 | < 200ms（100 条画线） | 页面加载到画线显示 |
| 实时推送延迟 | < 500ms（数据源到前端） | WebSocket 消息时间戳差 |
| SQLite 查询 | < 50ms（单股 K 线查询） | 后端日志 |

---

## 9. 部署规格

### 9.1 Docker Compose

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    volumes: ["./data:/app/data"]    # SQLite 持久化
    environment:
      - TZ=Asia/Shanghai
  frontend:
    build: ./frontend
    ports: ["3000:80"]               # nginx 静态服务
    depends_on: [backend]
```

### 9.2 启动命令

```bash
make dev    # 开发模式（前后端热重载）
make prod   # 生产模式（Docker Compose）
```

### 9.3 数据备份

```bash
make backup  # cp data/stock.db data/stock.db.bak.$(date +%Y%m%d)
```

---

## 10. 验收检查清单

| # | 检查项 | 对应需求 | 通过标准 |
|---|--------|---------|---------|
| 1 | 茅台月 K 10 年全貌 | F-01, F-02 | 月 K 显示 200+ 根，缩放流畅 |
| 2 | 日 K 2500 根缩放拖拽 | F-03, NF-01 | 无卡顿 |
| 3 | 画趋势线 → 刷新 → 恢复 | F-10, F-16 | 画线位置/颜色不变 |
| 4 | 画线切周 K 仍锚定 | F-18 | 位置跟随对应 K 线 |
| 5 | 打"买入"标注 → hover 显示 | F-30, F-32 | 绿色标记，浮层内容正确 |
| 6 | 标注导出 MD | F-37 | 文件可打开，格式正确 |
| 7 | 自选股分组 + 拖拽排序 | F-22, F-23 | 分组切换正常，排序持久 |
| 8 | 交易时段实时价格 | F-42 | 3s 刷新，红涨绿跌 |
| 9 | 数据源降级 | F-43 | 模拟 mootdx 断开，自动切 akshare |
| 10 | 手机操作全流程 | NF-04, NF-05 | iPhone Safari 完成 1-6 |
| 11 | Docker 一键启动 | NF-05 | `docker compose up` 后手机可访问 |
| 12 | 每日自动更新 | F-41 | 15:30 后当日数据入库 |
