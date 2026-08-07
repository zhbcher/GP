import { defineStore } from 'pinia'
import { ref } from 'vue'
import { drawingApi } from '@/api'
import type { DrawingData } from '@/types/drawing'
import { useUndo } from '@/composables/useUndo'

// Map chart overlay ID → backend drawing ID
const overlayToDrawingId = new Map<string, number>()

export const useDrawingStore = defineStore('drawing', () => {
  const drawings = ref<Map<number, DrawingData>>(new Map())
  const currentTool = ref<string | null>(null)
  const stockCode = ref('')
  const period = ref('daily')
  const subIndicator = ref<string>('VOL')  // FE-001: sub-chart indicator

  async function loadForStock(code: string, per = 'daily') {
    stockCode.value = code
    period.value = per
    const data = await drawingApi.list(code, per)
    drawings.value = new Map(data.map((d: any) => [d.id, d]))
  }

  async function create(data: { type: string; points: any[]; style?: Record<string, unknown> }) {
    const drawing = await drawingApi.create({
      stock_code: stockCode.value,
      period: period.value,
      ...data,
    } as any)
    drawings.value.set(drawing.id, drawing)
    useUndo().push({ type: 'drawing_create', data: drawing })
    return drawing
  }

  async function update(id: number, data: any) {
    const updated = await drawingApi.update(id, data)
    const existing = drawings.value.get(id)
    if (existing) {
      drawings.value.set(id, { ...existing, ...updated })
    }
  }

  async function remove(id: number) {
    const existing = drawings.value.get(id)
    await drawingApi.delete(id)
    drawings.value.delete(id)
    if (existing) {
      useUndo().push({ type: 'drawing_delete', data: existing })
    }
  }

  function linkOverlay(overlayId: string, drawingId: number) {
    overlayToDrawingId.set(overlayId, drawingId)
  }

  async function removeByOverlayId(overlayId: string) {
    const drawingId = overlayToDrawingId.get(overlayId)
    if (drawingId) {
      await remove(drawingId)
      overlayToDrawingId.delete(overlayId)
    }
  }

  function setTool(tool: string | null) {
    currentTool.value = tool
  }

  function setSubIndicator(ind: string) {
    subIndicator.value = ind
  }

  return {
    drawings, currentTool, stockCode, period, subIndicator,
    loadForStock, create, update, remove, removeByOverlayId, linkOverlay, setTool, setSubIndicator,
  }
})
