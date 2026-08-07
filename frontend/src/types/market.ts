// ---- 市场情绪看板相关类型 ----

export interface LimitUpItem {
  code: string
  name: string
  price?: number | null
  change_pct?: number | null
  limit_up_time?: string // 首次封板时间
  continuous?: number | null // 连板数
  reason?: string // 涨停题材/原因
}

export interface NorthFlowData {
  net_inflow?: number | null // 北向净流入（元）
  hgt?: number | null // 沪股通净流入（元）
  sgt?: number | null // 深股通净流入（元）
  updated_at?: string
}

export interface DragonTigerItem {
  code: string
  name: string
  change_pct?: number | null
  net_buy?: number | null // 净买入（元）
  buy_total?: number | null
  sell_total?: number | null
  reason?: string // 上榜原因
}

export interface SectorItem {
  name: string
  change_pct?: number | null
  lead_stock?: string // 领涨股
  net_inflow?: number | null // 主力净流入（元）
}

export interface HotRankItem {
  rank?: number | null
  code: string
  name: string
  heat?: number | null // 热度值
  change_pct?: number | null
}
