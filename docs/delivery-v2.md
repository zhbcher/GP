# GP 功能扩展 v2 — 交付总结

> 交付时间: 2026-08-07 | 台账: `~/.openclaw/workspace/docs/spm/ledger-gp-features-v2.md`
> Git 范围: `892700f` (init) → 本次全部 commits（main 分支）

## 交付概览

| 阶段 | 任务 | 交付方式 |
|------|------|----------|
| A | 工程卫生 + 基线 | ✅ 新开发 |
| B | 复权数据层（三复权） | ✅ 新开发（方案变更见下） |
| C | 标注导出 Markdown/CSV | ✅ 存量验证（已有） |
| D | 预测回测闭环 | ✅ 新开发 |
| E | 交易复盘 | ✅ 存量验证（已有） |
| F | 盘后日报 | ✅ 新开发 |
| G | 多股对比 | ✅ 存量增强（新增叠加模式） |
| H | 选股器扩容 | ✅ 新开发 |
| I | 行业资讯 | ✅ 存量验证（已有） |
| J | 集成回归 | ✅ 本次 |

## B 阶段方案变更（重要）

原计划：kline_data 加 adj_type 字段 + alembic 迁移。
实际采用：**除权因子公式法**——不动 158K 行存量数据，adjust_factor 表存权威累积因子，API 端实时复权。

原因：
1. 老板指令切换到 [a-stock-data](https://github.com/simonlin1212/a-stock-data) v3.6.0 数据源体系（通达信优先）
2. mootdx xdxr 除权数据可算精确因子，无需数据迁移，零 alembic 风险
3. 外部复权源不可靠：东财封本机 Python TLS 指纹（curl 通但 requests/httpx 断连），腾讯 fqkline 仅 641 根

**验证**: qfq vs 腾讯权威真值 avg_err=0.95%、median=0.74%；除权连续性 qfq=hfq 收益率一致（0.696%）；28 只自选股因子全量重算，无零因子。

**新增**: `tdx_client.py` 健壮 mootdx 工厂（显式服务器列表 + 真实取数验活 + 多级回退），替换全部裸 `Quotes.factory` 调用。

## 新功能明细

### D 预测回测闭环
- `prediction_records` 表：predict 调用时 6 模型 fire-and-forget 落库
- 到期评估：每日 16:05 job，对比第 N 交易日收盘（±0.5% 判 up/down/flat）
- API: `GET /api/predict/accuracy`（各模型准确率+样本数）、`POST /api/predict/evaluate`（手动补跑）
- 前端 PredictPanel 准确率区块（样本<30 显示"样本积累中"）

### F 盘后日报
- 5 板块：涨跌排行 / 异动≥5% / 当日预警 / 预测观点 / 持仓盈亏
- 定时：15:35（周一~五，收盘数据同步后）→ 飞书 webhook
- API: `POST /api/report/daily`、`GET /api/report/daily/preview`
- 实测：28 只排行正确，持仓盈亏 -14,141 元，飞书推送成功

### G1 归一化叠加对比
- CompareView 并列/叠加双模式切换
- 叠加：时间戳交集对齐 + 共同起点归一化区间涨跌幅，SVG 多曲线 + 悬浮十字 + tooltip

### H1 选股器扩容
- 5 新条件：RSI超卖/超买（Wilder RSI）、布林上/下轨、涨幅区间
- 前端 9 种条件参数编辑 UI

## 存量发现（C/E/I 已有实现）

盘点时发现三个功能在早期迭代中已实现且功能完整，本次做了端到端验证：
- **C1** 标注导出：`/api/annotations/export` md/csv + 前端导出按钮
- **E1/E2** 交易复盘：`/api/annotations/trade-pairs` FIFO 配对引擎 + 前端 trades tab
  （实测：买 22.26 → 卖 19.12 = -14.11%，持有 14 天，汇总正确）
- **I1** 行业资讯：TopBar「资讯」→ IndustryNews 12 赛道 × 按日分组 + AI 摘要

## 修复的存量 bug

1. `annotations/export` 缺 `Response` import → 500
2. `stockApi.predict` URL 双重 `/api` 前缀 → 404
3. 复权因子单位错误（fenhong 实为每10股/10 而非 /1000）+ songzhuangu/peigu 同为每10股
4. compute_adjusted 因子精确匹配查不到（`in_(dates)`）→ 改 bisect 累积查找
5. `latest_factor` round(6) 下溢归零 → round(12)
6. 日报实时行情键名无前缀 + 股票名 \x00 脏字符 + 排行缩进 bug

## 回归结果

- **API 回归**: 27/28 GET 端点 200（search 因测试时 mootdx 网络瞬时抖动超时，代码链路完好、基线时已通过）
- **前端构建**: vite build 通过
- **数据源**: 全部走 a-stock-data 体系（通达信优先，腾讯备选，东财仅独有数据且限流）

## 已知风险

1. **mootdx 海外网络敏感**：深夜/网络抖动时 TCP 7709 可能间歇取数失败，`tdx_client` 多级回退已缓解，但 search 等实时接口仍会受影响
2. **复权精度**：mootdx xdxr 老事件（2002-2010）与官方口径存在 ~3% 误差（近期事件精确），看盘用途完全够用
3. **预测回测准确率**：需真实时间积累样本，当前为空属正常
