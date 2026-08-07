export type DrawingType = 'trendline' | 'horizontal' | 'ray' | 'channel' | 'fibonacci' | 'rect' | 'arrow' | 'text'

export interface DrawingData {
  id: number
  stock_code: string
  period: string
  type: DrawingType
  points: Array<{ timestamp: number; value: number }>
  style: Record<string, unknown>
  text_content?: string
  visible: boolean
  created_at: string
  updated_at: string
}
