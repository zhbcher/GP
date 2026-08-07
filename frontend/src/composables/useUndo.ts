import { ref, computed } from 'vue'
import { drawingApi, annotationApi } from '@/api'
import type { DrawingData } from '@/types/drawing'
import type { Annotation } from '@/types/annotation'

const MAX_STACK = 20

export type UndoAction =
  | { type: 'drawing_create'; data: DrawingData }
  | { type: 'drawing_delete'; data: DrawingData }
  | { type: 'annotation_create'; data: Annotation }
  | { type: 'annotation_delete'; data: Annotation }

const stack = ref<UndoAction[]>([])
const canUndo = computed(() => stack.value.length > 0)

function push(action: UndoAction) {
  stack.value.push(action)
  if (stack.value.length > MAX_STACK) {
    stack.value.shift()
  }
}

async function undo() {
  const action = stack.value.pop()
  if (!action) return

  switch (action.type) {
    case 'drawing_create':
      // Undo create = delete the drawing
      await drawingApi.delete(action.data.id)
      break
    case 'drawing_delete':
      // Undo delete = re-create the drawing
      await drawingApi.create({
        stock_code: action.data.stock_code,
        period: action.data.period,
        type: action.data.type,
        points: action.data.points,
        style: action.data.style,
        text_content: action.data.text_content,
      })
      break
    case 'annotation_create':
      // Undo create = delete the annotation
      await annotationApi.delete(action.data.id)
      break
    case 'annotation_delete':
      // Undo delete = re-create the annotation
      await annotationApi.create({
        stock_code: action.data.stock_code,
        trade_date: action.data.trade_date,
        type: action.data.type,
        content: action.data.content,
        position: action.data.position,
        idempotency_key: `${action.data.stock_code}-${action.data.trade_date}-${action.data.type}-undo-${Date.now()}`,
      })
      break
  }
}

export function useUndo() {
  return { stack, canUndo, push, undo }
}
