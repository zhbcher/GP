import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { annotationApi } from '@/api'
import type { AnnotationType, AnnotationPosition, Annotation } from '@/types/annotation'
import { useUndo } from '@/composables/useUndo'

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

export interface PlacingTarget {
  tradeDate: string
  timestamp: number
  high: number
  low: number
}

export const useAnnotationStore = defineStore('annotation', () => {
  const annotations = ref<Map<string, Annotation>>(new Map())
  const mode = ref<'idle' | 'placing'>('idle')
  const visibility = ref<Record<AnnotationType, boolean>>({
    buy: true, sell: true, watch: true, review: true, other: true,
  })
  const stockCode = ref('')
  const selectedId = ref<string | null>(null)
  const placingTarget = ref<PlacingTarget | null>(null)

  const visibleAnnotations = computed(() =>
    Array.from(annotations.value.values()).filter(a => visibility.value[a.type as AnnotationType])
  )

  async function loadForStock(code: string) {
    stockCode.value = code
    const data = await annotationApi.list(code)
    annotations.value = new Map(data.map((a: Annotation) => [a.id, a]))
  }

  async function create(tradeDate: string, type: AnnotationType, content: string, position: AnnotationPosition) {
    const annotation = await annotationApi.create({
      stock_code: stockCode.value,
      trade_date: tradeDate,
      type,
      content,
      position,
      idempotency_key: `${stockCode.value}-${tradeDate}-${type}`,
    })
    annotations.value.set(annotation.id, annotation)
    useUndo().push({ type: 'annotation_create', data: annotation })
    mode.value = 'idle'
    return annotation
  }

  async function update(id: string, patch: Partial<Annotation>) {
    const updated = await annotationApi.update(id, patch)
    const existing = annotations.value.get(id)
    if (existing) {
      annotations.value.set(id, { ...existing, ...updated })
    }
  }

  async function remove(id: string) {
    const existing = annotations.value.get(id)
    await annotationApi.delete(id)
    annotations.value.delete(id)
    if (existing) {
      useUndo().push({ type: 'annotation_delete', data: existing })
    }
  }

  async function batchDelete() {
    await annotationApi.batchDelete(stockCode.value)
    annotations.value.clear()
  }

  function toggleVisibility(type: AnnotationType) {
    visibility.value[type] = !visibility.value[type]
  }

  function setMode(newMode: 'idle' | 'placing') {
    mode.value = newMode
    if (newMode === 'idle') {
      placingTarget.value = null
    }
  }

  function setPlacingTarget(target: PlacingTarget) {
    placingTarget.value = target
  }

  function getOverlayData(annotation: Annotation) {
    return {
      annotationId: annotation.id,
      type: annotation.type,
      content: annotation.content,
      position: annotation.position,
    }
  }

  function select(id: string | null) {
    selectedId.value = id
  }

  return {
    annotations, mode, visibility, stockCode, selectedId, placingTarget, visibleAnnotations,
    loadForStock, create, update, remove, batchDelete,
    toggleVisibility, setMode, setPlacingTarget, getOverlayData, select,
  }
})
