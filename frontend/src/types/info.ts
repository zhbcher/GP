// ---- 个股信息面板相关类型 ----

export interface ValuationSnapshot {
  pe?: number | null
  pb?: number | null
  total_market_cap?: number | null // 总市值（元）
  float_market_cap?: number | null // 流通市值（元）
  turnover_rate?: number | null // 换手率（%）
}

export interface FundFlowDetail {
  main_net_inflow?: number | null // 主力净流入（元）
  super_large_net?: number | null // 超大单净额
  large_net?: number | null // 大单净额
  medium_net?: number | null // 中单净额
  small_net?: number | null // 小单净额
}

export interface UnlockWarning {
  date?: string // 解禁日期
  shares?: number | null // 解禁股数
  ratio?: number | null // 占流通股比例（%）
  type?: string // 解禁类型
}

export interface StockOverview {
  code: string
  name?: string
  valuation?: ValuationSnapshot | null
  fund_flow?: FundFlowDetail | null
  concepts?: string[]
  unlock_warning?: UnlockWarning | null
}

export interface NewsItem {
  id?: string | number
  title: string
  time?: string // 发布时间
  source?: string
  url?: string
}

export interface AnnouncementItem {
  id?: string | number
  title: string
  date?: string
  type?: string // 公告类型
  is_negative?: boolean // 利空（减持/质押等）
  url?: string // PDF 链接
}

export interface ReportItem {
  id?: string | number
  title: string
  org?: string // 研究机构
  rating?: string // 评级：买入/增持/中性/减持/卖出
  date?: string
  url?: string
}

export interface ConsensusEstimate {
  eps?: number | null // 一致预期 EPS
  forward_pe?: number | null // 前向 PE
  peg?: number | null // PEG
}

export interface ReportsResponse {
  reports: ReportItem[]
  consensus?: ConsensusEstimate | null
}

export interface FinancePeriod {
  period?: string // 报告期，如 2024Q3
  revenue?: number | null // 营业收入（元）
  revenue_yoy?: number | null // 营收同比（%）
  net_profit?: number | null // 净利润（元）
  net_profit_yoy?: number | null // 净利同比（%）
  roe?: number | null // ROE（%）
  gross_margin?: number | null // 毛利率（%）
  debt_ratio?: number | null // 资产负债率（%）
  eps?: number | null // 每股收益
}

export interface DividendItem {
  year?: string
  plan?: string // 分红方案，如 10派5元
  ex_date?: string // 除权除息日
}

export interface FinanceData {
  indicators: FinancePeriod[]
  dividends?: DividendItem[]
}

export interface ShareStructureItem {
  name?: string
  ratio?: number | null // 占比（%）
}

export interface ShareholderCountChange {
  date?: string
  count?: number | null
  change_pct?: number | null // 环比变化（%）
}

export interface ProfileData {
  introduction?: string // 公司简介
  main_business?: string // 主营业务
  share_structure?: ShareStructureItem[]
  shareholder_count?: ShareholderCountChange[]
}
