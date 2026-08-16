<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { AnnotationType } from '@/types/annotation'
import { ANNOTATION_COLORS, ANNOTATION_LABELS } from '@/types/annotation'
import { useAnnotationStore } from '@/stores/annotation'

const annotationStore = useAnnotationStore()
const tooltip = ref<{
  visible: boolean
  x: number
  y: number
  annotationId: string
  type: AnnotationType
  content: string
  tradeDate: string
} | null>(null)

function onAnnotationHover(e: Event) {
  const detail = (e as CustomEvent).detail

  tooltip.value = {
    visible: true,
    x: detail.x || 0,
    y: detail.y || 0,
    annotationId: detail.annotationId,
    type: detail.type,
    content: detail.content,
    tradeDate: '',
  }
}

function onAnnotationHide() {
  tooltip.value = null
}

function onAnnotationClick(e: Event) {
  const detail = (e as CustomEvent).detail
  annotationStore.setMode('idle')
  annotationStore.select(detail.annotationId)
}

onMounted(() => {
  window.addEventListener('annotation-click', onAnnotationClick as EventListener)
  window.addEventListener('annotation-hover', onAnnotationHover as EventListener)
  window.addEventListener('annotation-hide', onAnnotationHide as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('annotation-click', onAnnotationClick)
  window.removeEventListener('annotation-hover', onAnnotationHover)
  window.removeEventListener('annotation-hide', onAnnotationHide)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="tooltip?.visible"
        class="annotation-tooltip"
        :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
      >
        <div class="tooltip-header">
          <span
            class="tooltip-dot"
            :style="{ background: ANNOTATION_COLORS[tooltip.type] }"
          />
          <span
            class="tooltip-type"
            :style="{ color: ANNOTATION_COLORS[tooltip.type] }"
          >
            {{ ANNOTATION_LABELS[tooltip.type] }}
          </span>
        </div>
        <div class="tooltip-content">
          {{ tooltip.content }}
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.annotation-tooltip {
  position: fixed;
  z-index: 1000;
  background: #1e2028;
  border: 1px solid #2e313a;
  border-radius: 8px;
  padding: 8px 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  pointer-events: auto;
  max-width: 280px;
  transform: translate(-50%, -100%);
  margin-top: -10px;
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.tooltip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.tooltip-type {
  font-size: 12px;
  font-weight: 600;
}

.tooltip-content {
  font-size: 13px;
  color: #e4e4e7;
  line-height: 1.4;
  word-break: break-word;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
