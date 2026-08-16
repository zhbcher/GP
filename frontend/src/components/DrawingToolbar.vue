<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useDrawingStore } from '@/stores/drawing'
import { useAnnotationStore, ANNOTATION_COLORS, ANNOTATION_LABELS } from '@/stores/annotation'
import { useStockStore } from '@/stores/stock'
import { usePredictStore } from '@/stores/predict'
import { getChart } from '@/overlays/annotationOverlay'
import { stockApi, dataIoApi } from '@/api'
import { useUndo } from '@/composables/useUndo'
import type { AnnotationType } from '@/types/annotation'

defineEmits<{
  'open-compare': []
}>()

const drawingStore = useDrawingStore()
const annotationStore = useAnnotationStore()
const stockStore = useStockStore()
const predictStore = usePredictStore()

// FE-005: screenshot export
function exportScreenshot() {
  const chart = getChart()
  if (!chart) return
  const url = chart.getConvertPictureUrl(true, 'png', '#181a20')
  const a = document.createElement('a')
  a.href = url
  a.download = `kline_${new Date().toISOString().slice(0, 10)}.png`
  a.click()
}

// FE-008: range statistics
const rangeMode = ref(false)
const rangeStart = ref<any>(null)
const rangeStats = ref<any>(null)

// ADV-001: multi-stock comparison
const { canUndo, undo } = useUndo()
const compareMode = ref(false)
const compareCode = ref('')

// MV-004: chips distribution toggle
const showChips = ref(false)
function toggleChips() {
  showChips.value = !showChips.value
  window.dispatchEvent(new CustomEvent('toggle-chips', { detail: { show: showChips.value } }))
}

async function toggleCompareMode() {
  compareMode.value = !compareMode.value
  if (!compareMode.value) {
    // Remove comparison overlay
    const chart = getChart()
    if (chart) {
      chart.removeOverlay({ name: 'compareLine' })
    }
    compareCode.value = ''
  }
}

async function addCompareStock() {
  if (!compareCode.value) return
  const chart = getChart()
  if (!chart) return

  try {
    // Fetch comparison stock kline
    const resp = await stockApi.getKline(compareCode.value, 'daily', 'qfq')
    const data = resp.data
    if (!data || data.length === 0) return

    // Normalize to percentage (first close = 100%)
    const baseClose = data[0].close
    const points = data.map((d: any) => ({
      timestamp: d.timestamp,
      value: (d.close / baseClose) * 100,
    }))

    // Create overlay line
    chart.createOverlay({
      name: 'compareLine',
      points: points,
      styles: {
        line: { color: '#f59e0b', size: 2 },
      },
      onRightClick: (event: any) => {
        chart.removeOverlay({ id: event.overlay.id })
        compareMode.value = false
        compareCode.value = ''
      },
    })

    compareMode.value = false
  } catch (e) {
    console.error('Compare stock failed:', e)
  }
}

// NV-003: JSON export/import
async function exportData() {
  const code = stockStore.currentStock?.stock_code
  if (!code) return
  try {
    const blob = await dataIoApi.export(code)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${code}_drawings_annotations.json`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Export failed:', e)
  }
}

const importFileInput = ref<HTMLInputElement | null>(null)

function triggerImport() {
  importFileInput.value?.click()
}

async function handleImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await dataIoApi.import(file)
    alert(`导入完成: 画线 ${result.imported_drawings} 条, 标注 ${result.imported_annotations} 条, 跳过 ${result.skipped} 条`)
    // Reload drawings and annotations for current stock
    if (stockStore.currentStock?.stock_code) {
      await drawingStore.loadDrawings(stockStore.currentStock.stock_code)
      await annotationStore.loadAnnotations(stockStore.currentStock.stock_code)
    }
  } catch (err) {
    console.error('Import failed:', err)
    alert('导入失败，请检查文件格式')
  }
  input.value = ''
}

function toggleRangeMode() {
  rangeMode.value = !rangeMode.value
  rangeStart.value = null
  rangeStats.value = null
  if (rangeMode.value) {
    drawingStore.setTool(null)
    annotationStore.setMode('idle')
  }
}

function onCandleBarClick(data: any) {
  if (!rangeMode.value) return
  const kData = data.kLineData
  if (!kData) return

  if (!rangeStart.value) {
    rangeStart.value = kData
  } else {
    // Calculate stats between rangeStart and current
    const kline = stockStore.klineData
    const t1 = Math.min(rangeStart.value.timestamp, kData.timestamp)
    const t2 = Math.max(rangeStart.value.timestamp, kData.timestamp)
    const slice = kline.filter(k => k.timestamp >= t1 && k.timestamp <= t2)
    if (slice.length >= 2) {
      const first = slice[0]
      const last = slice[slice.length - 1]
      const highs = slice.map(k => k.high)
      const lows = slice.map(k => k.low)
      const maxHigh = Math.max(...highs)
      const minLow = Math.min(...lows)
      const totalVol = slice.reduce((s, k) => s + k.volume, 0)
      const changePct = (last.close - first.open) / first.open * 100
      const amplitude = (maxHigh - minLow) / first.open * 100
      rangeStats.value = {
        startDate: new Date(t1).toLocaleDateString('zh-CN'),
        endDate: new Date(t2).toLocaleDateString('zh-CN'),
        bars: slice.length,
        changePct: changePct.toFixed(2),
        maxHigh: maxHigh.toFixed(2),
        minLow: minLow.toFixed(2),
        amplitude: amplitude.toFixed(2),
        totalVol: totalVol > 1e8 ? (totalVol / 1e8).toFixed(2) + '亿' : totalVol > 1e4 ? (totalVol / 1e4).toFixed(0) + '万' : String(totalVol),
      }
    }
    rangeMode.value = false
    rangeStart.value = null
  }
}

// FE-001: sub-chart indicator options
const subIndicators = ['VOL', 'MACD', 'KDJ', 'BOLL']

function switchSubIndicator(ind: string) {
  const chart = getChart()
  if (!chart) return
  // Remove existing sub-pane indicators
  const indicators = chart.getIndicators({ paneId: 'volume_pane' })
  for (const i of indicators) {
    chart.removeIndicator({ paneId: 'volume_pane', name: i.name })
  }
  chart.createIndicator({ name: ind, paneId: 'volume_pane' }, false)
  drawingStore.setSubIndicator(ind)
}

// Map our tool types to KLineChart v10 overlay names
const drawingTools = [
  { type: 'trendline', label: '趋势线', icon: '📏', overlay: 'straightLine' },
  { type: 'horizontal', label: '水平线', icon: '➖', overlay: 'horizontalStraightLine' },
  { type: 'ray', label: '射线', icon: '➡', overlay: 'rayLine' },
  { type: 'channel', label: '通道', icon: '📐', overlay: 'parallelStraightLine' },
  { type: 'fibonacci', label: '斐波那契', icon: '📊', overlay: 'fibonacciLine' },
  // FE-002: new drawing tools
  { type: 'rect', label: '矩形', icon: '⬜', overlay: 'rect' },
  { type: 'arrow', label: '箭头', icon: '↗', overlay: 'arrowLine' },
  { type: 'text', label: '文字', icon: '🔤', overlay: 'simpleAnnotation' },
]

function selectTool(tool: typeof drawingTools[0] | null) {
  const chart = getChart()
  if (!chart) return

  // If clicking the same tool, cancel drawing
  if (drawingStore.currentTool === tool?.type) {
    drawingStore.setTool(null)
    return
  }

  drawingStore.setTool(tool?.type || null)

  if (tool) {
    // Create overlay in drawing mode with magnet
    chart.createOverlay({
      name: tool.overlay,
      mode: 'weak_magnet',
      onDrawEnd: async (event: any) => {
        const overlay = event.overlay
        if (overlay && overlay.points && overlay.points.length > 0) {
          // Save to backend and link overlay ID
          const drawing = await drawingStore.create({
            type: tool.type,
            points: overlay.points.map((p: any) => ({
              timestamp: p.timestamp,
              value: p.value,
            })),
            style: overlay.styles || {},
          })
          drawingStore.linkOverlay(overlay.id, drawing.id)
        }
        drawingStore.setTool(null)
      },
      onRightClick: (event: any) => {
        // Right-click to delete the drawing + sync to backend
        chart.removeOverlay({ id: event.overlay.id })
        drawingStore.removeByOverlayId(event.overlay.id)
      },
    })
  }
}

function toggleAnnotationMode() {
  const newMode = annotationStore.mode === 'idle' ? 'placing' : 'idle'
  annotationStore.setMode(newMode)
}

// ESC to cancel drawing
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    drawingStore.setTool(null)
    annotationStore.setMode('idle')
  }
  // NV-005: Ctrl+Z / Cmd+Z undo
  if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
    e.preventDefault()
    undo()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  const chart = getChart()
  if (chart) {
    chart.subscribeAction('onCandleBarClick', onCandleBarClick)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  const chart = getChart()
  if (chart) {
    chart.unsubscribeAction('onCandleBarClick', onCandleBarClick)
  }
})
</script>

<template>
  <div class="drawing-toolbar">
    <div class="toolbar-divider">
      <span class="divider-label">副图</span>
      <button
        v-for="ind in subIndicators"
        :key="ind"
        :class="['tool-btn', { active: drawingStore.subIndicator === ind }]"
        @click="switchSubIndicator(ind)"
      >
        <span class="tool-label">{{ ind }}</span>
      </button>
    </div>

    <div class="toolbar-divider">
      <span class="divider-label">画线</span>
      <button
        v-for="tool in drawingTools"
        :key="tool.type"
        :class="['tool-btn', { active: drawingStore.currentTool === tool.type }]"
        :title="tool.label"
        @click="selectTool(tool)"
      >
        <span class="tool-icon">{{ tool.icon }}</span>
        <span class="tool-label">{{ tool.label }}</span>
      </button>
    </div>

    <div class="toolbar-divider">
      <span class="divider-label">工具</span>
      <button
        class="tool-btn"
        title="截图导出PNG"
        @click="exportScreenshot"
      >
        <span class="tool-icon">📷</span>
        <span class="tool-label">截图</span>
      </button>
      <button
        class="tool-btn"
        title="导出画线+标注JSON"
        @click="exportData"
      >
        <span class="tool-icon">📤</span>
        <span class="tool-label">导出</span>
      </button>
      <button
        class="tool-btn"
        title="导入画线+标注JSON"
        @click="triggerImport"
      >
        <span class="tool-icon">📥</span>
        <span class="tool-label">导入</span>
      </button>
      <input
        ref="importFileInput"
        type="file"
        accept=".json"
        style="display: none"
        @change="handleImportFile"
      >
      <button
        :class="['tool-btn', { active: rangeMode }]"
        title="区间统计：点击起始K线，再点击结束K线"
        @click="toggleRangeMode"
      >
        <span class="tool-icon">📊</span>
        <span class="tool-label">{{ rangeMode ? (rangeStart ? '点终点' : '点起点') : '区间' }}</span>
      </button>
      <button
        :class="['tool-btn', { active: compareMode }]"
        title="多股对比：输入股票代码叠加走势"
        @click="toggleCompareMode"
      >
        <span class="tool-icon">🔀</span>
        <span class="tool-label">对比</span>
      </button>
      <button
        class="tool-btn"
        title="同屏对比：多只股票并排显示"
        @click="$emit('open-compare')"
      >
        <span class="tool-icon">🗗</span>
        <span class="tool-label">同屏</span>
      </button>
      <button
        :class="['tool-btn', { active: showChips }]"
        title="筹码分布"
        @click="toggleChips"
      >
        <span class="tool-icon">🎯</span>
        <span class="tool-label">筹码</span>
      </button>
      <button
        :class="['tool-btn', { active: predictStore.visible }]"
        title="预测"
        @click="predictStore.toggle()"
      >
        <span class="tool-icon">📊</span>
        <span class="tool-label">预测</span>
      </button>
      <button
        class="tool-btn"
        :disabled="!canUndo"
        title="撤销 (Ctrl+Z)"
        @click="undo"
      >
        <span class="tool-icon">↩️</span>
        <span class="tool-label">撤销</span>
      </button>
    </div>

    <div class="toolbar-divider">
      <span class="divider-label">标注</span>
      <button
        :class="['tool-btn', { active: annotationStore.mode === 'placing' }]"
        title="标注"
        @click="toggleAnnotationMode"
      >
        <span class="tool-icon">📝</span>
        <span class="tool-label">标注</span>
      </button>

      <div class="annotation-filters">
        <button
          v-for="(color, type) in ANNOTATION_COLORS"
          :key="type"
          :class="['filter-btn', { active: annotationStore.visibility[type as AnnotationType] }]"
          :style="{ borderColor: color, color }"
          :title="`${ANNOTATION_LABELS[type as AnnotationType]} (${annotationStore.visibility[type as AnnotationType] ? '显示' : '隐藏'})`"
          @click="annotationStore.toggleVisibility(type as AnnotationType)"
        >
          {{ ANNOTATION_LABELS[type as AnnotationType] }}
        </button>
      </div>
    </div>
  </div>

  <!-- ADV-001: Compare stock input -->
  <Teleport to="body">
    <div
      v-if="compareMode"
      class="compare-popup"
    >
      <div class="compare-header">
        <span>输入对比股票代码</span>
        <button
          class="range-close"
          @click="compareMode = false"
        >
          ×
        </button>
      </div>
      <input
        v-model="compareCode"
        placeholder="例如: sz000858"
        @keyup.enter="addCompareStock"
      >
      <button
        class="save-btn"
        @click="addCompareStock"
      >
        叠加
      </button>
    </div>
  </Teleport>

  <!-- FE-008: Range statistics popup -->
  <Teleport to="body">
    <div
      v-if="rangeStats"
      class="range-popup"
    >
      <div class="range-header">
        <span>区间统计 {{ rangeStats.startDate }} ~ {{ rangeStats.endDate }}</span>
        <button
          class="range-close"
          @click="rangeStats = null"
        >
          ×
        </button>
      </div>
      <div class="range-grid">
        <div class="range-item">
          <span class="range-label">K线数</span><span class="range-value">{{ rangeStats.bars }}</span>
        </div>
        <div class="range-item">
          <span class="range-label">涨跌幅</span><span
            class="range-value"
            :class="Number(rangeStats.changePct) >= 0 ? 'text-up' : 'text-down'"
          >{{ rangeStats.changePct }}%</span>
        </div>
        <div class="range-item">
          <span class="range-label">最高</span><span class="range-value">{{ rangeStats.maxHigh }}</span>
        </div>
        <div class="range-item">
          <span class="range-label">最低</span><span class="range-value">{{ rangeStats.minLow }}</span>
        </div>
        <div class="range-item">
          <span class="range-label">振幅</span><span class="range-value">{{ rangeStats.amplitude }}%</span>
        </div>
        <div class="range-item">
          <span class="range-label">总成交量</span><span class="range-value">{{ rangeStats.totalVol }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.drawing-toolbar {
  display: flex;
  align-items: center;
  height: 40px;
  padding: 0 16px;
  background: #181a20;
  border-top: 1px solid #2e313a;
  gap: 16px;
  flex-shrink: 0;
}

.toolbar-divider {
  display: flex;
  align-items: center;
  gap: 4px;
}

.divider-label {
  font-size: 11px;
  color: #6b7280;
  margin-right: 4px;
}

.tool-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  background: transparent;
  color: #9ca3af;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}

.tool-btn:hover {
  color: #e4e4e7;
  background: #272a35;
}

.tool-btn.active {
  color: #3b82f6;
  background: #272a35;
  border-color: #3b82f6;
}

.tool-icon {
  font-size: 14px;
}

.tool-label {
  font-size: 12px;
}

.annotation-filters {
  display: flex;
  gap: 4px;
  margin-left: 8px;
}

.filter-btn {
  padding: 2px 8px;
  border-radius: 4px;
  background: transparent;
  border: 1px solid;
  cursor: pointer;
  font-size: 11px;
  opacity: 0.6;
  transition: all 0.15s;
}

.filter-btn:hover {
  opacity: 0.8;
}

.filter-btn.active {
  opacity: 1;
  font-weight: 600;
}

/* FE-008: Range statistics popup */
.range-popup {
  position: fixed;
  bottom: 60px;
  right: 320px;
  background: #1e2028;
  border: 1px solid #2e313a;
  border-radius: 8px;
  padding: 12px 16px;
  z-index: 1000;
  min-width: 240px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}

.range-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.range-close {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 16px;
  padding: 0 4px;
}

.range-close:hover { color: #ef4444; }

.range-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
}

.range-item {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.range-label { color: #6b7280; }
.range-value { color: #e4e4e7; font-family: monospace; }
.text-up { color: #ef4444; }
.text-down { color: #22c55e; }

/* ADV-001: Compare popup */
.compare-popup {
  position: fixed;
  bottom: 60px;
  right: 320px;
  background: #1e2028;
  border: 1px solid #2e313a;
  border-radius: 8px;
  padding: 12px 16px;
  z-index: 1000;
  min-width: 240px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}

.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 8px;
}

.compare-popup input {
  width: 100%;
  padding: 6px 8px;
  background: #0f1117;
  border: 1px solid #2e313a;
  border-radius: 4px;
  color: #e4e4e7;
  font-size: 12px;
  outline: none;
  margin-bottom: 8px;
}

.compare-popup input:focus {
  border-color: #3b82f6;
}
</style>