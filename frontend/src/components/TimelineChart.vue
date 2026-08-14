<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useStockStore } from '@/stores/stock'
import { stockApi } from '@/api'
import type { MinutePoint } from '@/types'

const stockStore = useStockStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const error = ref('')

let data: MinutePoint[] = []
let prevClose = 0
let ctx: CanvasRenderingContext2D | null = null
let dpr = window.devicePixelRatio || 1
let resizeObserver: ResizeObserver | null = null
let hoverIndex = -1

const PADDING = { top: 16, right: 70, bottom: 28, left: 8 }
const PRICE_RATIO = 0.68
const VOL_RATIO = 0.22
const GAP = 16

// 240 time slots: 09:30-11:29 (120) + 13:00-14:59 (120)
const TIME_SLOTS: string[] = []
for (let i = 0; i < 120; i++) {
  const total = 570 + i // 09:30 = 570 min
  TIME_SLOTS.push(`${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`)
}
for (let i = 0; i < 120; i++) {
  const total = 780 + i // 13:00 = 780 min
  TIME_SLOTS.push(`${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`)
}

function timeToIndex(time: string): number {
  const [h, m] = time.split(':').map(Number)
  const mins = h * 60 + m
  if (mins >= 570 && mins < 690) return mins - 570
  if (mins >= 780) return 120 + (mins - 780)
  return 0
}

async function loadData() {
  if (!stockStore.currentCode) return
  loading.value = true
  error.value = ''
  try {
    const resp = await stockApi.getTimeline(stockStore.currentCode)
    data = resp.data
    prevClose = resp.prev_close || 0
    
    // Check if market is closed (empty data with no error)
    if (!data || data.length === 0) {
      const now = new Date()
      const hour = now.getHours()
      const minute = now.getMinutes()
      const timeInMinutes = hour * 60 + minute
      
      // Market hours: 9:30-11:30, 13:00-15:00
      const isMarketOpen = (
        (timeInMinutes >= 570 && timeInMinutes <= 690) || // 9:30-11:30
        (timeInMinutes >= 780 && timeInMinutes <= 900)    // 13:00-15:00
      ) && now.getDay() >= 1 && now.getDay() <= 5 // Monday-Friday
      
      if (!isMarketOpen) {
        error.value = '市场已收盘'
      } else {
        error.value = '暂无分时数据'
      }
    }
    
    draw()
  } catch (e: any) {
    error.value = e?.message || '加载失败'
    data = []
    draw()
  } finally {
    loading.value = false
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !ctx) return
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)

  if (data.length === 0) {
    ctx.fillStyle = '#6b7280'
    ctx.font = '14px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(error.value || '暂无分时数据', w / 2, h / 2)
    return
  }

  const chartW = w - PADDING.left - PADDING.right
  const chartH = h - PADDING.top - PADDING.bottom
  const priceH = chartH * PRICE_RATIO
  const volH = chartH * VOL_RATIO
  const priceTop = PADDING.top
  const priceBottom = priceTop + priceH
  const volTop = priceBottom + GAP
  const volBottom = volTop + volH

  // Price range symmetric around prevClose
  let maxDiff = 0
  for (const p of data) {
    maxDiff = Math.max(maxDiff, Math.abs(p.price - prevClose))
    maxDiff = Math.max(maxDiff, Math.abs(p.avg_price - prevClose))
  }
  if (maxDiff === 0) maxDiff = 1
  const yScale = priceH / (maxDiff * 2)
  const yCenter = priceTop + priceH / 2
  const priceToY = (price: number) => yCenter - (price - prevClose) * yScale

  // Volume max
  let maxVol = 0
  for (const p of data) maxVol = Math.max(maxVol, p.volume)
  if (maxVol === 0) maxVol = 1
  const volToY = (vol: number) => volBottom - (vol / maxVol) * volH

  const xScale = chartW / 240
  const indexToX = (i: number) => PADDING.left + i * xScale + xScale / 2

  // --- Grid ---
  ctx.strokeStyle = '#222430'
  ctx.lineWidth = 1
  for (let i = 0; i <= 4; i++) {
    const y = priceTop + (priceH / 4) * i
    ctx.beginPath(); ctx.moveTo(PADDING.left, y); ctx.lineTo(PADDING.left + chartW, y); ctx.stroke()
  }
  for (let i = 0; i <= 2; i++) {
    const y = volTop + (volH / 2) * i
    ctx.beginPath(); ctx.moveTo(PADDING.left, y); ctx.lineTo(PADDING.left + chartW, y); ctx.stroke()
  }
  // Vertical time markers
  const timeMarks = [
    { idx: 0, label: '09:30' },
    { idx: 60, label: '10:30' },
    { idx: 120, label: '13:00' },
    { idx: 180, label: '14:00' },
    { idx: 239, label: '15:00' },
  ]
  ctx.fillStyle = '#6b7280'
  ctx.font = '11px monospace'
  ctx.textAlign = 'center'
  for (const tm of timeMarks) {
    const x = PADDING.left + tm.idx * xScale
    ctx.beginPath(); ctx.moveTo(x, priceTop); ctx.lineTo(x, volBottom); ctx.stroke()
    ctx.fillText(tm.label, x, h - 6)
  }

  // --- prev_close line ---
  ctx.strokeStyle = '#9ca3af'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 4])
  const ypc = priceToY(prevClose)
  ctx.beginPath(); ctx.moveTo(PADDING.left, ypc); ctx.lineTo(PADDING.left + chartW, ypc); ctx.stroke()
  ctx.setLineDash([])

  // --- Price line + fill ---
  const lastPrice = data[data.length - 1].price
  const isUp = lastPrice >= prevClose
  const lineColor = isUp ? '#ef4444' : '#22c55e'
  const fillStart = isUp ? 'rgba(239,68,68,0.15)' : 'rgba(34,197,94,0.15)'
  const fillEnd = isUp ? 'rgba(239,68,68,0.01)' : 'rgba(34,197,94,0.01)'

  // Fill area
  ctx.beginPath()
  for (let i = 0; i < data.length; i++) {
    const x = indexToX(timeToIndex(data[i].time))
    const y = priceToY(data[i].price)
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  }
  const lastX = indexToX(timeToIndex(data[data.length - 1].time))
  const firstX = indexToX(timeToIndex(data[0].time))
  ctx.lineTo(lastX, priceBottom)
  ctx.lineTo(firstX, priceBottom)
  ctx.closePath()
  const grad = ctx.createLinearGradient(0, priceTop, 0, priceBottom)
  grad.addColorStop(0, fillStart); grad.addColorStop(1, fillEnd)
  ctx.fillStyle = grad; ctx.fill()

  // Price line
  ctx.strokeStyle = lineColor
  ctx.lineWidth = 1.5
  ctx.beginPath()
  for (let i = 0; i < data.length; i++) {
    const x = indexToX(timeToIndex(data[i].time))
    const y = priceToY(data[i].price)
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  }
  ctx.stroke()

  // --- Avg price line (yellow dashed) ---
  ctx.strokeStyle = '#eab308'
  ctx.lineWidth = 1
  ctx.setLineDash([3, 3])
  ctx.beginPath()
  for (let i = 0; i < data.length; i++) {
    const x = indexToX(timeToIndex(data[i].time))
    const y = priceToY(data[i].avg_price)
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  }
  ctx.stroke()
  ctx.setLineDash([])

  // --- Volume bars ---
  for (let i = 0; i < data.length; i++) {
    const x = indexToX(timeToIndex(data[i].time))
    const vol = data[i].volume
    const y = volToY(vol)
    const barW = Math.max(1, xScale * 0.7)
    const up = data[i].price >= prevClose
    ctx.fillStyle = up ? 'rgba(239,68,68,0.7)' : 'rgba(34,197,94,0.7)'
    ctx.fillRect(x - barW / 2, y, barW, volBottom - y)
  }

  // --- Y-axis labels (right) ---
  ctx.font = '11px monospace'
  ctx.textAlign = 'left'
  const priceLabels = [
    { val: prevClose + maxDiff, y: priceTop },
    { val: prevClose + maxDiff / 2, y: priceTop + priceH / 4 },
    { val: prevClose, y: yCenter },
    { val: prevClose - maxDiff / 2, y: priceTop + priceH * 3 / 4 },
    { val: prevClose - maxDiff, y: priceBottom },
  ]
  for (const pl of priceLabels) {
    ctx.fillStyle = pl.val >= prevClose ? '#ef4444' : '#22c55e'
    ctx.fillText(pl.val.toFixed(2), PADDING.left + chartW + 4, pl.y + 4)
    const pct = ((pl.val - prevClose) / prevClose * 100).toFixed(2)
    ctx.fillText(`${pct}%`, PADDING.left + chartW + 4, pl.y + 16)
  }
  ctx.fillStyle = '#6b7280'
  ctx.fillText(String(maxVol), PADDING.left + chartW + 4, volTop + 4)

  // --- Crosshair ---
  if (hoverIndex >= 0 && hoverIndex < data.length) {
    const x = indexToX(timeToIndex(data[hoverIndex].time))
    const p = data[hoverIndex]

    ctx.strokeStyle = '#6b7280'
    ctx.lineWidth = 1
    ctx.setLineDash([2, 2])
    ctx.beginPath(); ctx.moveTo(x, priceTop); ctx.lineTo(x, volBottom); ctx.stroke()
    const y = priceToY(p.price)
    ctx.beginPath(); ctx.moveTo(PADDING.left, y); ctx.lineTo(PADDING.left + chartW, y); ctx.stroke()
    ctx.setLineDash([])

    // Price label
    ctx.fillStyle = p.price >= prevClose ? '#ef4444' : '#22c55e'
    ctx.fillRect(PADDING.left + chartW + 2, y - 9, 56, 18)
    ctx.fillStyle = '#fff'
    ctx.font = '11px monospace'
    ctx.textAlign = 'center'
    ctx.fillText(p.price.toFixed(2), PADDING.left + chartW + 30, y + 3)

    // Tooltip
    const tipX = PADDING.left + 8
    const tipY = priceTop + 8
    const tipW = 150
    const tipH = 92
    ctx.fillStyle = 'rgba(24,26,32,0.95)'
    ctx.strokeStyle = '#2e313a'
    ctx.fillRect(tipX, tipY, tipW, tipH)
    ctx.strokeRect(tipX, tipY, tipW, tipH)

    ctx.fillStyle = '#e4e4e7'
    ctx.font = '12px monospace'
    ctx.textAlign = 'left'
    const change = p.price - prevClose
    const changePct = (change / prevClose * 100).toFixed(2)
    ctx.fillText(`时间  ${p.time}`, tipX + 8, tipY + 16)
    ctx.fillText(`价格  ${p.price.toFixed(2)}`, tipX + 8, tipY + 32)
    ctx.fillStyle = change >= 0 ? '#ef4444' : '#22c55e'
    ctx.fillText(`涨跌  ${change >= 0 ? '+' : ''}${change.toFixed(2)} (${changePct}%)`, tipX + 8, tipY + 48)
    ctx.fillStyle = '#eab308'
    ctx.fillText(`均价  ${p.avg_price.toFixed(2)}`, tipX + 8, tipY + 64)
    ctx.fillStyle = '#9ca3af'
    ctx.fillText(`成交  ${p.volume}`, tipX + 8, tipY + 80)
  }
}

function onMouseMove(e: MouseEvent) {
  const canvas = canvasRef.value
  if (!canvas || data.length === 0) return
  const rect = canvas.getBoundingClientRect()
  const x = e.clientX - rect.left
  const w = canvas.clientWidth
  const chartW = w - PADDING.left - PADDING.right
  const xScale = chartW / 240
  const rawIdx = Math.floor((x - PADDING.left) / xScale)
  if (rawIdx >= 0 && rawIdx < 240) {
    // Find closest data point
    let best = -1
    let bestDist = 999
    for (let i = 0; i < data.length; i++) {
      const di = timeToIndex(data[i].time)
      const d = Math.abs(di - rawIdx)
      if (d < bestDist) { bestDist = d; best = i }
    }
    hoverIndex = best
    draw()
  }
}

function onMouseLeave() {
  hoverIndex = -1
  draw()
}

function onResize() { draw() }

onMounted(() => {
  const canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  canvas.addEventListener('mousemove', onMouseMove)
  canvas.addEventListener('mouseleave', onMouseLeave)
  resizeObserver = new ResizeObserver(onResize)
  resizeObserver.observe(canvas)
  window.addEventListener('select-stock', loadData as EventListener)
  if (stockStore.currentCode) loadData()
})

onUnmounted(() => {
  canvasRef.value?.removeEventListener('mousemove', onMouseMove)
  canvasRef.value?.removeEventListener('mouseleave', onMouseLeave)
  resizeObserver?.disconnect()
  window.removeEventListener('select-stock', loadData as EventListener)
})

watch(() => stockStore.currentCode, (code) => { if (code) loadData() })
</script>

<template>
  <div class="timeline-container">
    <canvas ref="canvasRef" class="timeline-canvas" />
    <div v-if="loading" class="loading-overlay">加载中...</div>
  </div>
</template>

<style scoped>
.timeline-container {
  flex: 1;
  position: relative;
  width: 100%;
  min-height: 0;
}
.timeline-canvas {
  width: 100%;
  height: 100%;
  display: block;
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
