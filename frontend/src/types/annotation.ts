export type AnnotationType = 'buy' | 'sell' | 'watch' | 'review' | 'other'
export type AnnotationPosition = 'above' | 'below'

export interface Annotation {
  id: string
  stock_code: string
  trade_date: string
  type: AnnotationType
  content: string
  position: AnnotationPosition
  created_at: string
  updated_at: string
}

export interface AnnotationExtendData {
  annotationId: string
  type: AnnotationType
  content: string
  position: AnnotationPosition
}

export const ANNOTATION_COLORS: Record<AnnotationType, string> = {
  buy: '#22c55e',
  sell: '#ef4444',
  watch: '#eab308',
  review: '#3b82f6',
  other: '#9ca3af',
}

export const ANNOTATION_LABELS: Record<AnnotationType, string> = {
  buy: '买入',
  sell: '卖出',
  watch: '关注',
  review: '复盘',
  other: '其他',
}

export interface AnnotationDisplayUpdate {
  stock_code: string
  type?: string
  visible: boolean
}
