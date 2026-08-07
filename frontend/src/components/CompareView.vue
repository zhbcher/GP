<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { init, dispose } from 'klinecharts'
import type { Chart } from 'klinecharts'
import { useWatchlistStore } from '@/stores/watchlist'
import { stockApi } from '@/api'
import type { PeriodType } from '@/types'

const emit = defineEmits<{ exit: [] }>()

const watchlistStore = useWatchlistStore()

const selectedStocks = ref<{ code: string; name: string }[]>([])
const period = ref<PeriodType>('daily')
const loading = ref(false)
const error = ref('')
const rootRef = ref<HTMLDivElement | null>(null)

let charts: Chart[] = []
let syncing = false
let loadToken = 0

const periods: { key: PeriodType; label: string }[] = [
  { key: '5min', label: '5分' },
  { key: '15min', label: '15分' },
  { key: '30min', label: '30分' },
  { key: '60min', label: '60分' },
  { key: 'daily', label: '日K' },
  { key: 'weekly', label: '周K' },
  { key: 'monthly', label: '月K' },
]

const periodLabel = computed(() => {
  return periods.find(p => p.key === period.value)?.label || period.value
})

const PERIOD_MAP: Record<string, { type: string; span: number }> = {
  '5min': { type: 'minute', span: 5 },
  '15min': { type: 'minute', span: 15 },
  '30min': { type: 'minute', span: 30 },
  '60min': { type: 'hour', span: 1 },
  daily: { type: 'day', span: 1 },
  weekly: { type: 'week', span: 1 },
  monthly: { type: 'month', span: 1 },
}

function toggleStock(stock: { stock_code: string; stock_name: string }) {
  const idx = selectedStocks.value.findIndex(s => s.code === stock.stock_code)
  if (idx >= 0) {
    selectedStocks.value.splice(idx, 1)
  } else if (selectedStocks.value.length < 4) {
    selectedStocks.value.push({ code: stock.stock_code, name: stock.stock_name })
  }

  if (selectedStocks.value.length >= 2) {
    if (viewMode.value === 'overlay') loadOverlayData()
    else loadChartData()
  } else if (charts.length > 0) {
    destroyCharts()
  }
}

function isStockSelected(code: string) {
  return selectedStocks.value.some(s => s.code === code)
}

function destroyCharts() {
  for (const c of charts) {
    if (c) {
      try { dispose(c) } catch { /* already disposed */ }
    }
  }
  charts = []
}

async function loadChartData() {
  if (selectedStocks.value.length < 2) {
    error.value = '请至少选择 2 只股票'
    return
  }
  error.value = ''

  const token = ++loadToken
  destroyCharts()
  await nextTick()

  if (token !== loadToken) return // stale request

  loading.value = true
  try {
    const containers = rootRef.value?.querySelectorAll('.compare-chart-container') || []

    for (let i = 0; i < selectedStocks.value.length; i++) {
      const stock = selectedStocks.value[i]
      const container = containers[i] as HTMLDivElement
      if (!container) continue

      // Clear any leftover DOM from disposed chart
      container.innerHTML = ''

      const chart = init(container, {
        styles: {
          grid: {
            show: true,
            horizontal: { show: true, color: '#2e313a', size: 1 },
            vertical: { show: true, color: '#2e313a', size: 1 },
          },
          candle: {
            type: 'candle_solid',
            bar: {
              upColor: '#ef4444',
              downColor: '#22c55e',
              noChangeColor: '#9ca3af',
              upBorderColor: '#ef4444',
              downBorderColor: '#22c55e',
              upWickColor: '#ef4444',
              downWickColor: '#22c55e',
            },
            tooltip: { showRule: 'follow_cross', showType: 'standard' },
            priceMark: {
              show: true,
              high: { show: true, color: '#9ca3af', textSize: 10 },
              low: { show: true, color: '#9ca3af', textSize: 10 },
              last: { show: false },
            },
          },
          crosshair: {
            show: true,
            horizontal: { show: true, line: { style: { style: 'dashed', size: 1, color: '#4b5563' } } },
            vertical: { show: true, line: { style: { style: 'dashed', size: 1, color: '#4b5563' } } },
          },
          xAxis: {
            show: true,
            axisLine: { show: true, color: '#2e313a' },
            tickLine: { show: false },
            tickText: { show: true, color: '#6b7280', size: 10 },
          },
          yAxis: {
            show: true,
            axisLine: { show: true, color: '#2e313a' },
            tickLine: { show: false },
            tickText: { show: true, color: '#6b7280', size: 10 },
          },
          separator: { size: 1, color: '#2e313a' },
        },
      })

      if (!chart) continue

      chart.setLocale('zh-CN')
      chart.setTimezone('Asia/Shanghai')

      // Volume sub-chart
      chart.createIndicator({ name: 'VOL', paneId: 'volume_pane' }, false)
      // Main chart MA indicator
      chart.createIndicator({ name: 'MA', paneId: 'candle_pane' }, true)

      // Fetch kline data
      const resp = await stockApi.getKline(stock.code, period.value, 'qfq')
      if (token !== loadToken) return // stale

      const data = resp.data.map((d: any) => ({
        timestamp: d.timestamp,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
        volume: d.volume,
        turnover: d.turnover,
      }))

      chart.setSymbol({ ticker: stock.code, pricePrecision: 2, volumePrecision: 0 })
      chart.setPeriod(PERIOD_MAP[period.value] || PERIOD_MAP.daily)
      chart.applyNewData(data)

      charts.push(chart)
    }

    setupSync()
  } catch (e) {
    console.error('Failed to load compare data:', e)
    error.value = '加载数据失败，请重试'
  } finally {
    if (token === loadToken) {
      loading.value = false
    }
  }
}

function setupSync() {
  for (let i = 0; i < charts.length; i++) {
    const chart = charts[i]
    if (!chart) continue

    const onZoom = () => {
      if (syncing) return
      syncing = true
      syncOtherCharts(i)
      requestAnimationFrame(() => { syncing = false })
    }

    const onScroll = () => {
      if (syncing) return
      syncing = true
      syncOtherCharts(i)
      requestAnimationFrame(() => { syncing = false })
    }

    chart.subscribeAction('onZoom', onZoom)
    chart.subscribeAction('onScroll', onScroll)
  }
}

function syncOtherCharts(sourceIdx: number) {
  const source = charts[sourceIdx]
  if (!source) return

  const range = (source as any).getVisibleRange?.()
  if (!range) return

  const dataList = (source as any).getDataList?.() || []
  const fromIdx = Math.max(0, Math.floor(range.from ?? 0))
  const fromTimestamp = dataList[fromIdx]?.timestamp
  if (!fromTimestamp) return

  const sourceBars = (range.to ?? 0) - (range.from ?? 0)

  for (let i = 0; i < charts.length; i++) {
    if (i === sourceIdx) continue
    const target = charts[i]
    if (!target) continue

    // Sync scroll position
    target.scrollToTimestamp(fromTimestamp)

    // Best-effort zoom sync: adjust zoom if visible bar count differs
    const targetRange = (target as any).getVisibleRange?.()
    if (targetRange) {
      const targetBars = (targetRange.to ?? 0) - (targetRange.from ?? 0)
      if (sourceBars > 0 && targetBars > 0 && Math.abs(sourceBars - targetBars) > 1) {
        const factor = targetBars / sourceBars
        ;(target as any).zoomAtCoordinate?.(factor)
      }
    }
  }
}

function onPeriodChange(p: PeriodType) {
  period.value = p
  if (viewMode.value === 'overlay') loadOverlayData()
  else loadChartData()
}

function onResize() {
  for (const chart of charts) {
    chart?.resize()
  }
}

// ===== G1: 归一化叠加对比模式 =====
const viewMode = ref<'grid' | 'overlay'>('grid')
interface OverlaySeries { code: string; name: string; color: string; ts: number[]; pct: number[] }
const overlaySeries = ref<OverlaySeries[]>([])
const overlayLoading = ref(false)
const overlayCanvasRef = ref<HTMLDivElement | null>(null)
const COMPARE_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#eab308']
const hoverIdx = ref<number | null>(null)

const overlayRender = ref<{
  w: number; h: number;
  paths: { color: string; d: string; name: string; last: number }[];
  yTicks: { y: number; label: string }[];
  xTicks: { x: number; label: string }[];
  zeroY: number | null;
  baseTs: number[];
}>({ w: 800, h: 400, paths: [], yTicks: [], xTicks: [], zeroY: null, baseTs: [] })

async function loadOverlayData() {
  if (selectedStocks.value.length < 2) return
  overlayLoading.value = true
  try {
    const all = await Promise.all(selectedStocks.value.map(st =>
      stockApi.getKline(st.code, period.value, 'qfq')
        .then(r => ({ code: st.code, name: st.name, bars: r.data as any[] }))
    ))
    // 时间戳交集对齐
    const sets = all.map(a => new Set(a.bars.map(b => b.timestamp)))
    let common = [...sets[0]]
    for (const st of sets.slice(1)) common = common.filter(t => st.has(t))
    common.sort((a, b) => a - b)
    common = common.slice(-250)
    if (common.length < 2) { overlaySeries.value = []; return }
    overlaySeries.value = all.map((a, i) => {
      const map = new Map(a.bars.map(b => [b.timestamp, b.close]))
      const ts = common.filter(t => map.has(t))
      const base = (map.get(ts[0]) as number) || 1
      return {
        code: a.code, name: a.name,
        color: COMPARE_COLORS[i % COMPARE_COLORS.length],
        ts, pct: ts.map(t => ((map.get(t) as number) / base - 1) * 100),
      }
    })
    nextTick(renderOverlay)
  } catch (e) {
    console.error('overlay load failed:', e)
    overlaySeries.value = []
  } finally {
    overlayLoading.value = false
  }
}

function renderOverlay() {
  const el = overlayCanvasRef.value
  const series = overlaySeries.value
  if (!el || series.length === 0) return
  const w = el.clientWidth || 800
  const h = el.clientHeight || 400
  const padL = 48, padR = 12, padT = 12, padB = 22
  const baseTs = series[0].ts
  const n = baseTs.length
  const allPct = series.flatMap(sr => sr.pct)
  let min = Math.min(...allPct), max = Math.max(...allPct)
  if (max - min < 1) { const mid = (max + min) / 2; min = mid - 1; max = mid + 1 }
  const pad = (max - min) * 0.06
  min -= pad; max += pad
  const xOf = (i: number) => padL + (i / Math.max(1, n - 1)) * (w - padL - padR)
  const yOf = (v: number) => padT + (1 - (v - min) / (max - min)) * (h - padT - padB)
  const paths = series.map(sr => ({
    name: sr.name, color: sr.color,
    last: sr.pct[sr.pct.length - 1],
    d: sr.pct.map((v, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(' '),
  }))
  const yTicks: { y: number; label: string }[] = []
  for (let k = 0; k <= 4; k++) {
    const v = min + (k / 4) * (max - min)
    yTicks.push({ y: yOf(v), label: `${v.toFixed(1)}%` })
  }
  const fmt = (ts: number) => {
    const d = new Date(ts)
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }
  const xTicks: { x: number; label: string }[] = []
  for (let k = 0; k <= 4; k++) {
    const i = Math.round((k / 4) * (n - 1))
    xTicks.push({ x: xOf(i), label: fmt(baseTs[i]) })
  }
  overlayRender.value = {
    w, h, paths, yTicks, xTicks,
    zeroY: min < 0 && max > 0 ? yOf(0) : null,
    baseTs,
  }
}

function onOverlayMove(e: MouseEvent) {
  const r = overlayRender.value
  const el = overlayCanvasRef.value
  if (!el || r.baseTs.length === 0) return
  const padL = 48, padR = 12
  const n = r.baseTs.length
  const x = e.clientX - el.getBoundingClientRect().left
  const idx = Math.round(((x - padL) / Math.max(1, r.w - padL - padR)) * (n - 1))
  hoverIdx.value = Math.max(0, Math.min(n - 1, idx))
}

const hoverInfo = computed(() => {
  const i = hoverIdx.value
  if (i === null || overlaySeries.value.length === 0) return null
  const d = new Date(overlaySeries.value[0].ts[i])
  const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return {
    date: dateStr,
    x: 48 + (i / Math.max(1, overlaySeries.value[0].ts.length - 1)) * (overlayRender.value.w - 60),
    items: overlaySeries.value.map(sr => ({ name: sr.name, color: sr.color, pct: sr.pct[i] })),
  }
})

function switchMode(m: 'grid' | 'overlay') {
  viewMode.value = m
  if (m === 'overlay') loadOverlayData()
  else if (selectedStocks.value.length >= 2) loadChartData()
}

const origOnResize = onResize
function onResizeAll() {
  origOnResize()
  if (viewMode.value === 'overlay') renderOverlay()
}

onMounted(() => {
  window.addEventListener('resize', onResizeAll)
  // Pre-select first 2 stocks from watchlist
  const stocks = watchlistStore.allStocks
  if (stocks.length >= 2) {
    selectedStocks.value = [
      { code: stocks[0].stock_code, name: stocks[0].stock_name },
      { code: stocks[1].stock_code, name: stocks[1].stock_name },
    ]
  }
  loadChartData()
})

onUnmounted(() => {
  window.removeEventListener('resize', onResizeAll)
  destroyCharts()
})
</script>

<template>
  <div class="compare-view" ref="rootRef">
    <!-- Top bar: stock selector + period + exit -->
    <div class="compare-topbar">
      <div class="stock-selector">
        <span class="selector-label">选择股票 ({{ selectedStocks.length }}/4):</span>
        <div class="stock-chips">
          <button
            v-for="stock in watchlistStore.allStocks"
            :key="stock.stock_code"
            :class="['stock-chip', { selected: isStockSelected(stock.stock_code) }]"
            @click="toggleStock(stock)"
          >
            {{ stock.stock_name }}
            <span class="chip-code">{{ stock.stock_code }}</span>
          </button>
        </div>
      </div>

      <div class="period-selector">
        <button
          v-for="p in periods"
          :key="p.key"
          :class="['period-btn', { active: period === p.key }]"
          @click="onPeriodChange(p.key)"
        >
          {{ p.label }}
        </button>
      </div>

      <div class="mode-selector">
        <button :class="['period-btn', { active: viewMode === 'grid' }]" @click="switchMode('grid')">并列</button>
        <button :class="['period-btn', { active: viewMode === 'overlay' }]" @click="switchMode('overlay')">叠加</button>
      </div>

      <button class="exit-btn" @click="emit('exit')">退出对比</button>
    </div>

    <!-- Chart area -->
    <div class="compare-charts" v-if="viewMode === 'grid'">
      <div v-if="loading" class="loading-overlay">加载中...</div>
      <div v-if="error" class="error-overlay">{{ error }}</div>

      <div
        v-for="stock in selectedStocks"
        :key="stock.code"
        class="compare-chart-item"
      >
        <div class="chart-label">{{ stock.name }} ({{ stock.code }}) · {{ periodLabel }}</div>
        <div class="compare-chart-container"></div>
      </div>
    </div>

    <!-- G1: 归一化叠加对比 -->
    <div class="overlay-wrap" v-else>
      <div v-if="overlayLoading" class="loading-overlay">加载中...</div>
      <div class="overlay-legend">
        <span v-for="sr in overlaySeries" :key="sr.code" class="legend-item">
          <i class="legend-dot" :style="{ background: sr.color }"></i>
          {{ sr.name }} <b :style="{ color: sr.color }">{{ sr.pct[sr.pct.length - 1] >= 0 ? '+' : '' }}{{ sr.pct[sr.pct.length - 1]?.toFixed(2) }}%</b>
        </span>
        <span class="legend-hint">（区间涨跌幅，以共同起点归一化）</span>
      </div>
      <div class="overlay-canvas" ref="overlayCanvasRef" @mousemove="onOverlayMove" @mouseleave="hoverIdx = null">
        <svg :width="overlayRender.w" :height="overlayRender.h">
          <line v-for="(t, i) in overlayRender.yTicks" :key="'y' + i"
            :x1="48" :x2="overlayRender.w - 12" :y1="t.y" :y2="t.y" stroke="#2e313a" stroke-width="1" />
          <text v-for="(t, i) in overlayRender.yTicks" :key="'yt' + i"
            :x="42" :y="t.y + 3" text-anchor="end" fill="#6b7280" font-size="10">{{ t.label }}</text>
          <text v-for="(t, i) in overlayRender.xTicks" :key="'x' + i"
            :x="t.x" :y="overlayRender.h - 6" text-anchor="middle" fill="#6b7280" font-size="10">{{ t.label }}</text>
          <line v-if="overlayRender.zeroY !== null"
            :x1="48" :x2="overlayRender.w - 12" :y1="overlayRender.zeroY" :y2="overlayRender.zeroY"
            stroke="#6b7280" stroke-dasharray="3,3" stroke-width="1" />
          <path v-for="(p, i) in overlayRender.paths" :key="'p' + i" :d="p.d" :stroke="p.color" fill="none" stroke-width="1.6" />
          <line v-if="hoverInfo" :x1="hoverInfo.x" :x2="hoverInfo.x" :y1="12" :y2="overlayRender.h - 22"
            stroke="#4b5563" stroke-dasharray="2,2" stroke-width="1" />
        </svg>
        <div v-if="hoverInfo" class="hover-tooltip" :style="{ left: Math.min(hoverInfo.x + 10, overlayRender.w - 150) + 'px' }">
          <div class="tt-date">{{ hoverInfo.date }}</div>
          <div v-for="it in hoverInfo.items" :key="it.name" class="tt-row">
            <i class="legend-dot" :style="{ background: it.color }"></i>{{ it.name }}
            <b>{{ it.pct >= 0 ? '+' : '' }}{{ it.pct.toFixed(2) }}%</b>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.compare-view {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: #0f1117;
}

.compare-topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: #181a20;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.stock-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.selector-label {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
}

.stock-chips {
  display: flex;
  gap: 4px;
  overflow-x: auto;
  flex: 1;
}

.stock-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 4px;
  background: #272a35;
  color: #9ca3af;
  border: 1px solid #2e313a;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  transition: all 0.15s;
}

.stock-chip:hover {
  color: #e4e4e7;
  border-color: #3b82f6;
}

.stock-chip.selected {
  color: #3b82f6;
  border-color: #3b82f6;
  background: rgba(59, 130, 246, 0.15);
}

.chip-code {
  font-size: 10px;
  color: #6b7280;
  font-family: monospace;
}

.stock-chip.selected .chip-code {
  color: #3b82f6;
}

.period-selector {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.period-btn {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: transparent;
  color: #9ca3af;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}

.period-btn:hover {
  color: #e4e4e7;
  background: #272a35;
}

.period-btn.active {
  color: #3b82f6;
  background: #272a35;
}

.exit-btn {
  padding: 6px 16px;
  border-radius: 6px;
  background: #ef4444;
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
  transition: all 0.15s;
}

.exit-btn:hover {
  background: #dc2626;
}

.compare-charts {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.loading-overlay,
.error-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 10;
  font-size: 14px;
  background: rgba(15, 17, 23, 0.8);
  padding: 12px 24px;
  border-radius: 8px;
}

.loading-overlay {
  color: #9ca3af;
}

.error-overlay {
  color: #ef4444;
}

.compare-chart-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-bottom: 1px solid #2e313a;
  position: relative;
}

.compare-chart-item:last-child {
  border-bottom: none;
}

.chart-label {
  position: absolute;
  top: 4px;
  left: 8px;
  z-index: 5;
  font-size: 12px;
  color: #9ca3af;
  background: rgba(24, 26, 32, 0.8);
  padding: 2px 8px;
  border-radius: 4px;
  pointer-events: none;
}

.mode-selector { display: flex; gap: 2px; flex-shrink: 0; border: 1px solid #2e313a; border-radius: 6px; padding: 2px; }
.overlay-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }
.overlay-legend { display: flex; align-items: center; gap: 14px; padding: 8px 16px 4px; flex-wrap: wrap; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #e4e4e7; }
.legend-item b { font-family: monospace; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.legend-hint { font-size: 11px; color: #6b7280; }
.overlay-canvas { flex: 1; position: relative; min-height: 300px; }
.overlay-canvas svg { display: block; width: 100%; height: 100%; }
.hover-tooltip {
  position: absolute; top: 12px; background: #1c1f27; border: 1px solid #2e313a;
  border-radius: 6px; padding: 6px 10px; font-size: 11px; pointer-events: none; z-index: 10;
}
.tt-date { color: #9ca3af; margin-bottom: 4px; }
.tt-row { display: flex; align-items: center; gap: 6px; color: #e4e4e7; padding: 1px 0; }
.tt-row b { margin-left: auto; font-family: monospace; }

.compare-chart-container {
  flex: 1;
  width: 100%;
  min-height: 0;
}
</style>
