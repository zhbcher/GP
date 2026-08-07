export type { AnnotationType, AnnotationPosition, Annotation, AnnotationExtendData, AnnotationDisplayUpdate } from './annotation'
export type { DrawingType, DrawingData } from './drawing'
export type {
  ValuationSnapshot, FundFlowDetail, UnlockWarning, StockOverview,
  NewsItem, AnnouncementItem, ReportItem, ConsensusEstimate, ReportsResponse,
  FinancePeriod, DividendItem, FinanceData,
  ShareStructureItem, ShareholderCountChange, ProfileData,
} from './info'
export type {
  LimitUpItem, NorthFlowData, DragonTigerItem, SectorItem, HotRankItem,
} from './market'

export interface RealtimeQuote {
  price: number
  change_pct: number
  volume: number
  high: number
  low: number
  open: number
  prev_close: number
  pe?: number
  pb?: number
  market_cap?: number
}

export interface StockInfo {
  code: string
  name: string
  pinyin?: string
}

export interface WatchlistWithRealtime {
  id: number
  stock_code: string
  stock_name: string
  group_id: number | null
  note: string
  sort_order: number
  created_at: string
  realtime: any | null
}

export interface GroupRead {
  id: number
  name: string
  sort_order: number
  created_at: string
}

export type PeriodType = 'timeline' | 'minute' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly' | 'yearly'
export type AdjustType = 'qfq' | 'hfq' | 'none'

export interface KlineData {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover: number
}

export interface KlineResponse {
  code: string
  name: string
  period: string
  adjust: string
  data: KlineData[]
  count: number
}

export interface MinutePoint {
  time: string
  price: number
  avg_price: number
  volume: number
}

export interface MinuteResponse {
  code: string
  name: string
  prev_close: number
  data: MinutePoint[]
  count: number
  error?: string
}

export interface TimelineResponse {
  code: string
  name: string
  prev_close: number
  data: MinutePoint[]
  count: number
  error?: string
}

export interface Period {
  type: PeriodType
  span: number
}

export interface ChipItem {
  price: number
  ratio: number
}

export interface ChipDistribution {
  code: string
  current_price: number
  chips: ChipItem[]
  profit_ratio: number
  avg_cost: number
}

// ---- Industry news (P4) ----
export interface IndustryNewsItem {
  id?: number
  title: string
  title_zh?: string
  link: string
  date: string
  published_at?: string
  summary: string
  content?: string
  content_zh?: string
  source: string
  sector: string
}

export interface NewsSectorInfo {
  sector: string
  count: number
}

export interface NewsDayInfo {
  date: string
  count: number
  has_digest: boolean
}

export interface NewsSectorsResponse {
  sectors: NewsSectorInfo[]
  refreshing: boolean
}

export interface NewsSectorDaysResponse {
  sector: string
  days: NewsDayInfo[]
}

export interface NewsSectorDayDetail {
  sector: string
  date: string
  digest: string[]
  items: IndustryNewsItem[]
}
