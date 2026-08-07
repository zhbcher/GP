import { defineStore } from 'pinia'
import { ref } from 'vue'
import { stockApi } from '@/api'

export interface EnsembleVote {
  direction: number
  confidence: number
  weight: number
}

export interface EnsembleResult {
  final_trend: string
  weighted_confidence: number
  score: number
  model_weights: Record<string, number>
  votes: Record<string, EnsembleVote>
  target_price: number | null
  status: string
}

export interface PredictResult {
  code: string
  current_price: number
  models: Record<string, any>
  ensemble: EnsembleResult | { error: string; status?: string }
  llm?: {
    status: string
    summary?: string
    suggestion?: string
    risk?: string
    confidence?: number
    cached?: boolean
  }
}

export const usePredictStore = defineStore('predict', () => {
  const result = ref<PredictResult | null>(null)
  const loading = ref(false)
  const error = ref('')
  const visible = ref(false)  // 预测叠加层显示/隐藏

  async function load(code: string, days = 5, llm = false) {
    loading.value = true
    error.value = ''
    try {
      result.value = await stockApi.predict(code, days, llm)
    } catch (e: any) {
      error.value = e.message || '预测失败'
      result.value = null
    } finally {
      loading.value = false
    }
  }

  function toggle() {
    visible.value = !visible.value
  }

  function show() {
    visible.value = true
  }

  function hide() {
    visible.value = false
  }

  return { result, loading, error, visible, load, toggle, show, hide }
})