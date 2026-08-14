import axios from 'axios'
import type {
  Annotation as AnnotationType, AnnotationDisplayUpdate, KlineResponse, MinuteResponse, TimelineResponse, StockInfo,
  StockOverview, NewsItem, AnnouncementItem, ReportsResponse, FinanceData, ProfileData,
  LimitUpItem, NorthFlowData, DragonTigerItem, SectorItem, HotRankItem,
  NewsSectorsResponse, NewsSectorDaysResponse, NewsSectorDayDetail,
  ChipDistribution,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
})

// ---- Access key management ----
const KEY_STORAGE = 'stock_access_key'

export function getAccessKey(): string | null {
  return localStorage.getItem(KEY_STORAGE)
}

export function setAccessKey(key: string) {
  localStorage.setItem(KEY_STORAGE, key)
}

export function clearAccessKey() {
  localStorage.removeItem(KEY_STORAGE)
}

/**
 * On page load, check URL for ?key=*** and persist it.
 * This allows bookmark-based access: http://domain/?key=***
 */
export function initKeyFromUrl() {
  const params = new URLSearchParams(window.location.search)
  const urlKey = params.get('key')
  if (urlKey) {
    setAccessKey(urlKey)
    // Clean URL (remove key param)
    params.delete('key')
    const clean = params.toString()
      ? `${window.location.pathname}?${params.toString()}`
      : window.location.pathname
    window.history.replaceState({}, '', clean)
  }
}

// Request interceptor: attach access key
api.interceptors.request.use((config) => {
  const key = getAccessKey()
  if (key) {
    config.headers.Authorization = `Bearer ${key}`
  }
  return config
})

// Response interceptor: clear key on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      clearAccessKey()
      window.dispatchEvent(new CustomEvent('auth-expired'))
    }
    return Promise.reject(err)
  },
)

export const authApi = {
  check(): Promise<{ auth_enabled: boolean }> {
    return api.get('/auth/check').then(r => r.data)
  },
  verify(key: string): Promise<{ ok: boolean }> {
    return api.post('/auth/verify', { key }).then(r => r.data)
  },
}

export const stockApi = {
  search(q: string): Promise<StockInfo[]> {
    return api.get(`/stock/search`, { params: { q, limit: 20 } }).then(r => r.data)
  },
  getKline(code: string, period = 'daily', adjust = 'qfq', limit = 2500): Promise<KlineResponse> {
    return api.get(`/stock/${code}/kline`, { params: { period, adjust, limit } }).then(r => r.data)
  },

  getOversoldSignals(code: string): Promise<any> {
    return api.get(`/stock/${code}/oversold-signals`).then(r => r.data)
  },

  getMinute(code: string): Promise<MinuteResponse> {
    return api.get(`/stock/${code}/minute`).then(r => r.data)
  },
  getSignals(code: string): Promise<{ code: string, date?: string, base: any[], consolidation: any[] }> {
    return api.get(`/stock/${code}/signals`).then(r => r.data)
  },
  getTimeline(code: string): Promise<TimelineResponse> {
    return api.get(`/stock/${code}/timeline`).then(r => r.data)
  },
  predict(code: string, days = 5, llm = false) {
    return api.get(`/stock/${code}/predict`, { params: { days, ...(llm ? { llm: true } : {}) } }).then(r => r.data)
  },
}

export interface ModelAccuracy {
  model: string
  samples: number
  correct: number
  accuracy: number
}

export interface BacktestStat { total: number; correct: number; accuracy: number; source?: string }

export const predictApi = {
  accuracy(): Promise<{ models: ModelAccuracy[]; count: number }> {
    return api.get('/predict/accuracy').then(r => r.data)
  },
  backtest(): Promise<{ horizons: Record<string, Record<string, BacktestStat>>; report: string | null }> {
    return api.get('/predict/backtest').then(r => r.data)
  },
}

export const watchlistApi = {
  list(): Promise<any[]> {
    return api.get('/watchlist').then(r => r.data)
  },
  create(data: { stock_code: string; stock_name: string; note?: string; group_id?: number }) {
    return api.post('/watchlist', data).then(r => r.data)
  },
  update(id: number, data: any) {
    return api.put(`/watchlist/${id}`, data).then(r => r.data)
  },
  delete(id: number) {
    return api.delete(`/watchlist/${id}`).then(r => r.data)
  },
  listGroups() {
    return api.get('/watchlist/groups').then(r => r.data)
  },
  createGroup(name: string) {
    return api.post('/watchlist/groups', { name }).then(r => r.data)
  },
  updateGroup(id: number, data: any) {
    return api.put(`/watchlist/groups/${id}`, data).then(r => r.data)
  },
  deleteGroup(id: number) {
    return api.delete(`/watchlist/groups/${id}`).then(r => r.data)
  },
  importCodes(codes: string[]): Promise<{ imported: { code: string; name: string }[]; skipped: string[]; not_found: string[] }> {
    return api.post('/watchlist/import', { codes }).then(r => r.data)
  },
}

export const drawingApi = {
  list(stock_code: string, period = 'daily'): Promise<any[]> {
    return api.get('/drawings', { params: { stock_code, period } }).then(r => r.data)
  },
  create(data: { stock_code: string; period: string; type: string; points: any[]; style?: Record<string, unknown>; text_content?: string; idempotency_key?: string }) {
    return api.post('/drawings', data).then(r => r.data)
  },
  update(id: number, data: any) {
    return api.put(`/drawings/${id}`, data).then(r => r.data)
  },
  delete(id: number) {
    return api.delete(`/drawings/${id}`).then(r => r.data)
  },
}

export const annotationApi = {
  list(stock_code: string): Promise<AnnotationType[]> {
    return api.get('/annotations', { params: { stock_code } }).then(r => r.data)
  },
  create(data: {
    stock_code: string
    trade_date: string
    type: string
    content: string
    position: string
    idempotency_key?: string
  }) {
    return api.post('/annotations', data, {
      headers: { 'Idempotency-Key': data.idempotency_key || '' },
    }).then(r => r.data)
  },
  update(id: string, data: Partial<AnnotationType>) {
    return api.put(`/annotations/${id}`, data).then(r => r.data)
  },
  delete(id: string) {
    return api.delete(`/annotations/${id}`).then(r => r.data)
  },
  batchDelete(stock_code: string) {
    return api.delete(`/annotations?stock_code=${stock_code}`).then(r => r.data)
  },
  toggleDisplay(data: AnnotationDisplayUpdate) {
    return api.patch('/annotations/display', data).then(r => r.data)
  },
  export(stock_code: string, format = 'md') {
    return api.get(`/annotations/export`, { params: { stock_code, format }, responseType: 'blob' }).then(r => r.data)
  },
  timeline(days = 30): Promise<{ timeline: { date: string; annotations: { id: string; stock_code: string; stock_name: string; type: string; content: string; trade_date: string }[] }[] }> {
    return api.get('/annotations/timeline', { params: { days } }).then(r => r.data)
  },
}

export const journalApi = {
  get(date: string): Promise<any> {
    return api.get('/journal', { params: { date } }).then(r => r.data)
  },
  upsert(data: { trade_date: string; operations: string; market_obs: string; plan: string; mood: string }): Promise<any> {
    return api.put('/journal', data).then(r => r.data)
  },
  recent(days = 30): Promise<any[]> {
    return api.get('/journal/recent', { params: { days } }).then(r => r.data)
  },
  annotations(date: string): Promise<any[]> {
    return api.get(`/journal/${date}/annotations`).then(r => r.data)
  },
}

export const alertApi = {
  list(stock_code?: string): Promise<any[]> {
    return api.get('/alerts', { params: stock_code ? { stock_code } : {} }).then(r => r.data)
  },
  create(data: {
    stock_code: string
    stock_name?: string
    alert_type?: string
    target_price?: number
    direction?: string
    pct_threshold?: number
    volume_ratio?: number
    volume_days?: number
  }) {
    return api.post('/alerts', data).then(r => r.data)
  },
  delete(id: number) {
    return api.delete(`/alerts/${id}`).then(r => r.data)
  },
}

export const positionApi = {
  summary(): Promise<{ market_value: number; total_cost: number; total_profit: number; profit_pct: number; position_count: number; stock_count: number }> {
    return api.get('/positions/summary').then(r => r.data)
  },
  list(stock_code?: string): Promise<any[]> {
    return api.get('/positions', { params: stock_code ? { stock_code } : {} }).then(r => r.data)
  },
  create(data: { stock_code: string; stock_name?: string; cost_price: number; quantity: number; buy_date?: string; note?: string }) {
    return api.post('/positions', data).then(r => r.data)
  },
  update(id: number, data: any) {
    return api.put(`/positions/${id}`, data).then(r => r.data)
  },
  delete(id: number) {
    return api.delete(`/positions/${id}`).then(r => r.data)
  },
}

export const backupApi = {
  download() {
    return api.get('/backup', { responseType: 'blob' }).then(r => r.data)
  },
  restore(file: File) {
    const form = new FormData()
    form.append('file', file)
    return api.post('/backup', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
  },
}

export const healthApi = {
  check() {
    return api.get('/health').then(r => r.data)
  },
}

export const infoApi = {
  overview(code: string): Promise<StockOverview> {
    return api.get(`/info/${code}/overview`).then(r => r.data)
  },
  news(code: string, limit = 20): Promise<NewsItem[]> {
    return api.get(`/info/${code}/news`, { params: { limit } }).then(r => r.data)
  },
  announcements(code: string, limit = 30): Promise<AnnouncementItem[]> {
    return api.get(`/info/${code}/announcements`, { params: { limit } }).then(r => r.data)
  },
  reports(code: string, limit = 10): Promise<ReportsResponse> {
    return api.get(`/info/${code}/reports`, { params: { limit } }).then(r => r.data)
  },
  finance(code: string): Promise<FinanceData> {
    return api.get(`/info/${code}/finance`).then(r => r.data)
  },
  profile(code: string): Promise<ProfileData> {
    return api.get(`/info/${code}/profile`).then(r => r.data)
  },
}

export const marketApi = {
  limitUp(): Promise<LimitUpItem[]> {
    return api.get('/market/limit-up').then(r => r.data)
  },
  northFlow(): Promise<NorthFlowData> {
    return api.get('/market/north-flow').then(r => r.data)
  },
  dragonTiger(date?: string): Promise<DragonTigerItem[]> {
    return api.get('/market/dragon-tiger', { params: date ? { date } : {} }).then(r => r.data)
  },
  sectors(): Promise<SectorItem[]> {
    return api.get('/market/sectors').then(r => r.data)
  },
  hotRank(): Promise<HotRankItem[]> {
    return api.get('/market/hot-rank').then(r => r.data)
  },
}

export const screenApi = {
  screen(conditions: any[]): Promise<{ results: any[]; total: number }> {
    return api.post('/watchlist/screen', { conditions }).then(r => r.data)
  },
}

export const chipsApi = {
  getDistribution(code: string, days = 120, decay = 0.95): Promise<ChipDistribution> {
    return api.get(`/stock/${code}/chips`, { params: { days, decay } }).then(r => r.data)
  },
}

export const dataIoApi = {
  export(stockCode: string): Promise<Blob> {
    return api.get('/export', { params: { stock_code: stockCode }, responseType: 'blob' }).then(r => r.data)
  },
  exportAll(): Promise<Blob> {
    return api.get('/export/all', { responseType: 'blob' }).then(r => r.data)
  },
  import(file: File): Promise<{ imported_drawings: number; imported_annotations: number; skipped: number }> {
    const form = new FormData()
    form.append('file', file)
    return api.post('/import', form, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data)
  },
}

export const newsApi = {
  sectors(): Promise<NewsSectorsResponse> {
    return api.get('/news/sectors').then(r => r.data)
  },
  sectorDays(sector: string): Promise<NewsSectorDaysResponse> {
    return api.get(`/news/sector/${sector}/days`).then(r => r.data)
  },
  sectorDay(sector: string, date: string): Promise<NewsSectorDayDetail> {
    return api.get(`/news/sector/${sector}/day/${date}`).then(r => r.data)
  },
  refresh(): Promise<{ ok: boolean; message?: string }> {
    return api.post('/news/refresh').then(r => r.data)
  },
}