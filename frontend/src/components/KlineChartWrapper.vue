<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useStockStore } from '@/stores/stock'
import { useAnnotationStore } from '@/stores/annotation'
import { useDrawingStore } from '@/stores/drawing'
import {
  createChart, getChart, resizeChart, destroyChart,
  registerAnnotationOverlay, registerLimitMarkOverlay, registerMinuteAvgOverlay,
  createAnnotationOverlay, clearAllOverlays, markLimitCandles, createMinuteAvgOverlay,
  registerSignalMarkOverlay,
} from '@/overlays/annotationOverlay'
import { stockApi } from '@/api'
import type { MinutePoint } from '@/types'

const stockStore = useStockStore()
const annotationStore = useAnnotationStore()
const drawingStore = useDrawingStore()
const containerRef = ref<HTMLDivElement | null>(null)
const loading = ref(false)

// Track current stock for DataLoader
let currentCode = ''
let currentPeriod = 'daily'
let currentAdjust = 'qfq'
let minutePrevClose = 0

onMounted(async () => {
  window.addEventListener('select-stock', onSelectStock as EventListener)
  window.addEventListener('open-annotation-editor', onOpenEditor as EventListener)
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onKeyDown)

  if (containerRef.value) {
    createChart(containerRef.value)
    registerAnnotationOverlay()
    registerLimitMarkOverlay()
    registerMinuteAvgOverlay()
    registerSignalMarkOverlay()
    setupDataLoader()
    setupChartActions()
  }
})

onUnmounted(() => {
  window.removeEventListener('select-stock', onSelectStock as EventListener)
  window.removeEventListener('open-annotation-editor', onOpenEditor as EventListener)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onKeyDown)
  destroyChart()
})

// Delete/Backspace removes the last non-annotation overlay (drawing) + syncs to backend
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Delete' || e.key === 'Backspace') {
    const tag = (e.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return

    const chart = getChart()
    if (!chart) return
    const overlays = chart.getOverlays().filter(o => o.name !== 'stockAnnotation')
    if (overlays.length > 0) {
      const last = overlays[overlays.length - 1]
      chart.removeOverlay({ id: last.id })
      drawingStore.removeByOverlayId(last.id)
    }
  }
}

function onResize() {
  resizeChart()
}

// Store minute avg data for overlay drawing
let minuteAvgData: { timestamp: number; avg: number }[] = []

/**
 * v10 DataLoader: chart pulls data via getBars callback instead of applyNewData.
 * On resetData(), chart calls getBars with type='init'.
 */
function setupDataLoader() {
  const chart = getChart()
  if (!chart) return

  chart.setDataLoader({
    getBars: async (params) => {
      const { type, callback } = params
      if (type === 'init' && currentCode) {
        loading.value = true
        try {
          if (currentPeriod === 'minute') {
            // Minute chart: fetch intraday data
            const resp = await stockApi.getMinute(currentCode)
            minutePrevClose = resp.prev_close
            if (resp.data.length === 0) {
              callback([], false)
              return
            }
            const data = minuteDataToKline(resp.data, resp.prev_close)
            // Store avg data for overlay
            const today = new Date()
            today.setHours(0, 0, 0, 0)
            const baseTs = today.getTime()
            minuteAvgData = resp.data.map((p) => {
              const [h, m] = p.time.split(':').map(Number)
              return { timestamp: baseTs + (h * 60 + m) * 60 * 1000, avg: p.avg_price }
            })
            applyMinuteChartStyles()
            callback(data, false)
            // Draw avg price line overlay after data is rendered
            setTimeout(() => {
              createMinuteAvgOverlay(minuteAvgData.map(d => ({ timestamp: d.timestamp, value: d.avg })))
            }, 100)
          } else {
            // K-line chart (daily/weekly/monthly/yearly + minute K-line periods)
            restoreKlineChartStyles()
            const adjust = MINUTE_KLINE_PERIODS.includes(currentPeriod) ? 'none' : currentAdjust
            const resp = await stockApi.getKline(currentCode, currentPeriod, adjust)
            const data = resp.data.map((d: any) => ({
              timestamp: d.timestamp,
              open: d.open,
              high: d.high,
              low: d.low,
              close: d.close,
              volume: d.volume,
              turnover: d.turnover,
            }))
            stockStore.setKline(resp.data)
            callback(data, false)

            // Load annotations and drawings after data is set
            await annotationStore.loadForStock(currentCode)
            syncAnnotationOverlays()
            await drawingStore.loadForStock(currentCode, currentPeriod)
            restoreDrawings()
            // FE-007: mark limit-up/down candles
            markLimitCandles(data)
            // 超跌反弹信号（不影响 K 线）
            stockApi.getOversoldSignals(currentCode).then((sigData: any) => {
              drawOversoldSignals(data, sigData)
            }).catch(() => {})
          }
        } catch (e) {
          console.error('Failed to load data:', e)
          callback([], false)
        } finally {
          loading.value = false
        }
      } else {
        callback([], false)
      }
    },
  })
}

function setupChartActions() {
  const chart = getChart()
  if (!chart) return

  chart.subscribeAction('onCandleBarClick', (data: any) => {
    if (annotationStore.mode !== 'placing') return
    const kData = data.kLineData
    if (!kData) return

    const d = new Date(kData.timestamp)
    const tradeDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

    annotationStore.setPlacingTarget({
      tradeDate,
      timestamp: kData.timestamp,
      high: kData.high,
      low: kData.low,
    })

    window.dispatchEvent(new CustomEvent('open-annotation-editor', {
      detail: { tradeDate, timestamp: kData.timestamp, high: kData.high },
    }))
  })
}

/**
 * Convert minute data to KLineChart-compatible format.
 * Uses synthetic timestamps for today so X-axis renders correctly.
 * Stores avg_price as extra field for the MINUTE_AVG indicator.
 */
function minuteDataToKline(points: MinutePoint[], prevClose: number) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const baseTs = today.getTime()

  return points.map((p, i) => {
    // Parse HH:MM to minutes offset
    const [h, m] = p.time.split(':').map(Number)
    const ts = baseTs + (h * 60 + m) * 60 * 1000
    return {
      timestamp: ts,
      open: p.price,
      high: p.price,
      low: p.price,
      close: p.price,
      volume: p.volume,
      turnover: 0,
      avg_price: p.avg_price,
    }
  })
}

/**
 * Apply chart styles for minute (intraday) view:
 * - Area candle type
 * - prev_close reference line
 * - Symmetric Y-axis around prev_close
 * - Hide MA indicators, show MINUTE_AVG
 */
function applyMinuteChartStyles() {
  const chart = getChart()
  if (!chart) return

  // Switch to area candle
  chart.setStyles({
    candle: {
      type: 'area',
      area: {
        lineSize: 1.5,
        lineColor: '#3b82f6',
        value: 'close',
        smooth: false,
        backgroundColor: [{
          offset: 0,
          color: 'rgba(59, 130, 246, 0.25)',
        }, {
          offset: 1,
          color: 'rgba(59, 130, 246, 0.02)',
        }],
      },
      priceMark: { last: { show: true } },
    },
    indicator: {
      lastValueMark: { show: false },
    },
  })

  // Remove standard indicators (MA, EMA, BOLL) for clean minute view
  try {
    chart.removeIndicator({ name: 'MA' })
    chart.removeIndicator({ name: 'EMA' })
    chart.removeIndicator({ name: 'BOLL' })
  } catch (e) {
    // indicators may not exist, ignore
  }

  // Add prev_close horizontal line via overlay
  if (minutePrevClose > 0) {
    chart.createOverlay({
      name: 'horizontalStraightLine',
      points: [{ value: minutePrevClose }],
      styles: {
        line: { color: '#9ca3af', size: 1, style: 'dashed' },
      },
      lock: true,
      visible: true,
      zLevel: -1,
    })
  }
}

/**
 * Restore standard K-line chart styles when leaving minute view.
 */
function restoreKlineChartStyles() {
  const chart = getChart()
  if (!chart) return

  chart.setStyles({
    candle: {
      type: 'candle_solid',
      priceMark: { last: { show: true } },
    },
  })

  // Remove minute-specific overlays (horizontal prev_close lines)
  const overlays = chart.getOverlays()
  for (const o of overlays) {
    if (o.name === 'horizontalStraightLine' && o.lock) {
      chart.removeOverlay({ id: o.id })
    }
  }
  // Remove minute avg indicator (if any)
  try {
    chart.removeIndicator({ name: 'MINUTE_AVG' })
  } catch (e) {
    // ignore
  }
  minuteAvgData = []
}

const PERIOD_MAP: Record<string, { type: string; span: number }> = {
  '5min': { type: 'minute', span: 5 },
  '15min': { type: 'minute', span: 15 },
  '30min': { type: 'minute', span: 30 },
  '60min': { type: 'hour', span: 1 },
  daily: { type: 'day', span: 1 },
  weekly: { type: 'week', span: 1 },
  monthly: { type: 'month', span: 1 },
  yearly: { type: 'year', span: 1 },
}

const MINUTE_KLINE_PERIODS = ['5min', '15min', '30min', '60min']

async function onSelectStock(e: Event) {
  const { code, name } = (e as CustomEvent).detail
  currentCode = code
  currentPeriod = stockStore.period
  currentAdjust = stockStore.adjust
  stockStore.setStock(code, name)

  const chart = getChart()
  if (chart) {
    clearAllOverlays()
    // v10: must setSymbol + setPeriod before resetData triggers DataLoader
    chart.setSymbol({ ticker: code, pricePrecision: 2, volumePrecision: 0 })
    chart.setPeriod(PERIOD_MAP[currentPeriod] || PERIOD_MAP.daily)
    chart.resetData()
  }
}

function syncAnnotationOverlays() {
  const chart = getChart()
  if (!chart || !stockStore.currentCode) return

  clearAllOverlays()

  for (const ann of annotationStore.visibleAnnotations) {
    const klineItem = stockStore.klineData.find(k => {
      const d = new Date(k.timestamp)
      const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      return dateStr === ann.trade_date
    })
    if (klineItem) {
      createAnnotationOverlay({
        annotationId: ann.id,
        type: ann.type,
        content: ann.content,
        position: ann.position,
        timestamp: klineItem.timestamp,
        value: ann.position === 'below' ? klineItem.low : klineItem.high,
      })
    }
  }
}

// 超跌反弹信号 overlay
function drawOversoldSignals(klineData: any[], sigData: any) {
  try {
    const chart = getChart()
    if (!chart || !sigData) return
    chart.removeOverlay({ name: 'signalDot' })
    chart.removeOverlay({ name: 'signalTriangle' })
    for (const k of klineData) {
      const d = new Date(k.timestamp)
      const ds = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
      if (sigData.date && ds === sigData.date) {
        const base = sigData.base || {}
        const consol = sigData.consolidation || {}
        if (base['11'] && base['11'].found) {
          chart.createOverlay({ name: 'signalDot', points: [{ timestamp: k.timestamp, value: k.low }], extendData: { kind: 'base' }, visible: true })
        }
        if (consol['11'] && consol['11'].found) {
          chart.createOverlay({ name: 'signalTriangle', points: [{ timestamp: k.timestamp, value: k.low }], extendData: { kind: 'consolidation' }, visible: true })
        }
        return
      }
    }
  } catch (e) { /* ignore */ }
}

function restoreDrawings() {
  const chart = getChart()
  if (!chart) return

  const allOverlays = chart.getOverlays()
  for (const o of allOverlays) {
    if (o.name !== 'stockAnnotation') {
      chart.removeOverlay({ id: o.id })
    }
  }

  const typeMap: Record<string, string> = {
    trendline: 'straightLine',
    horizontal: 'horizontalStraightLine',
    ray: 'rayLine',
    channel: 'parallelStraightLine',
    fibonacci: 'fibonacciLine',
  }

  for (const [, drawing] of drawingStore.drawings) {
    if (!drawing.visible) continue
    const overlayName = typeMap[drawing.type] || drawing.type
    try {
      const overlayId = chart.createOverlay({
        name: overlayName,
        points: drawing.points.map(p => ({ timestamp: p.timestamp, value: p.value })),
        styles: drawing.style || {},
        onRightClick: (event: any) => {
          chart.removeOverlay({ id: event.overlay.id })
          drawingStore.removeByOverlayId(event.overlay.id)
        },
      })
      // Link chart overlay ID → backend drawing ID for delete sync
      if (typeof overlayId === 'string') {
        drawingStore.linkOverlay(overlayId, drawing.id)
      }
    } catch (e) {
      console.warn(`Failed to restore drawing ${drawing.id}:`, e)
    }
  }
}

function onOpenEditor(e: Event) {
  const detail = (e as CustomEvent).detail
  annotationStore.setMode('idle')
  annotationStore.selectedId = detail?.annotationId || null
}

watch(
  () => [annotationStore.annotations.size, JSON.stringify(annotationStore.visibility)],
  () => {
    if (stockStore.currentCode) {
      syncAnnotationOverlays()
    }
  }
)

async function changePeriod(p: 'minute' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly' | 'yearly') {
  currentPeriod = p
  stockStore.setPeriod(p)
  const chart = getChart()
  if (chart && currentCode) {
    clearAllOverlays()
    if (p === 'minute') {
      chart.setPeriod({ type: 'minute', span: 1 })
    } else {
      chart.setPeriod(PERIOD_MAP[p] || PERIOD_MAP.daily)
    }
    chart.resetData()
  }
}

async function changeAdjust(a: 'qfq' | 'hfq' | 'none') {
  currentAdjust = a
  stockStore.setAdjust(a)
  const chart = getChart()
  if (chart && currentCode) {
    clearAllOverlays()
    chart.resetData()
  }
}

defineExpose({ changePeriod, changeAdjust })
</script>

<template>
  <div class="chart-wrapper" ref="containerRef">
    <div v-if="loading" class="loading-overlay">加载中...</div>
  </div>
</template>

<style scoped>
.chart-wrapper {
  flex: 1;
  position: relative;
  width: 100%;
  min-height: 0;
}

.loading-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #9ca3af;
  font-size: 14px;
  z-index: 10;
}
</style>