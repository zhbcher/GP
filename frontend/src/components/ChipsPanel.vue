<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useStockStore } from '@/stores/stock'
import { chipsApi } from '@/api'
import type { ChipDistribution, ChipItem } from '@/types'

const stockStore = useStockStore()
const canvasRef = ref<HTMLCanvasElement | null>(null)
const loading = ref(false)
const chipData = ref<ChipDistribution | null>(null)

// Y-axis price range — sync with K-line visible range
const priceMin = ref(0)
const priceMax = ref(0)

// Panel config
const PANEL_WIDTH = 120
const PRICE_STEPS = 80 // number of price rows for rendering

let resizeObserver: ResizeObserver | null = null

async function fetchChips() {
  if (!stockStore.currentCode) return
  loading.value = true
  try {
    const data = await chipsApi.getDistribution(stockStore.currentCode, 120, 0.95)
    chipData.value = data
    // Compute price range from chips data + current price
    if (data.chips.length > 0) {
      const prices = data.chips.map(c => c.price)
      const lo = Math.min(...prices, data.current_price)
      const hi = Math.max(...prices, data.current_price)
      // Add 5% padding
      const pad = (hi - lo) * 0.05 || hi * 0.01
      priceMin.value = lo - pad
      priceMax.value = hi + pad
    }
    await nextTick()
    draw()
  } catch (e) {
    console.error('Failed to fetch chips:', e)
  } finally {
    loading.value = false
  }
}

// Also compute price range from kline data (fallback / sync with K-line)
function updatePriceRangeFromKline() {
  const kline = stockStore.klineData
  if (kline.length === 0) return
  // Use recent 120 bars (or all if fewer)
  const recent = kline.slice(-120)
  const highs = recent.map(k => k.high)
  const lows = recent.map(k => k.low)
  const hi = Math.max(...highs)
  const lo = Math.min(...lows)
  const pad = (hi - lo) * 0.05 || hi * 0.01
  priceMin.value = lo - pad
  priceMax.value = hi + pad
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const W = rect.width
  const H = rect.height

  // Clear
  ctx.fillStyle = '#181a20'
  ctx.fillRect(0, 0, W, H)

  if (!chipData.value || chipData.value.chips.length === 0) {
    ctx.fillStyle = '#6b7280'
    ctx.font = '11px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('暂无筹码数据', W / 2, H / 2)
    return
  }

  const data = chipData.value
  const pMin = priceMin.value
  const pMax = priceMax.value
  const pRange = pMax - pMin
  if (pRange <= 0) return

  // Top padding for labels
  const PAD_TOP = 20
  const PAD_BOTTOM = 10
  const chartH = H - PAD_TOP - PAD_BOTTOM

  // Price → Y mapping
  function priceToY(price: number): number {
    return PAD_TOP + ((pMax - price) / pRange) * chartH
  }

  // Find max ratio for scaling
  const maxRatio = Math.max(...data.chips.map(c => c.ratio), 0.001)

  // Draw horizontal bars
  const barAreaWidth = W - 8 // leave 8px right padding
  for (const chip of data.chips) {
    const y = priceToY(chip.price)
    const barLen = (chip.ratio / maxRatio) * barAreaWidth
    const isProfit = chip.price <= data.current_price
    ctx.fillStyle = isProfit ? 'rgba(34, 197, 94, 0.35)' : 'rgba(239, 68, 68, 0.35)'
    ctx.fillRect(0, y - 1, barLen, 2)
  }

  // Draw current price line
  const cpY = priceToY(data.current_price)
  ctx.strokeStyle = '#f59e0b'
  ctx.lineWidth = 1
  ctx.setLineDash([4, 2])
  ctx.beginPath()
  ctx.moveTo(0, cpY)
  ctx.lineTo(W, cpY)
  ctx.stroke()
  ctx.setLineDash([])

  // Draw avg cost line
  const acY = priceToY(data.avg_cost)
  ctx.strokeStyle = '#8b5cf6'
  ctx.lineWidth = 1
  ctx.setLineDash([2, 2])
  ctx.beginPath()
  ctx.moveTo(0, acY)
  ctx.lineTo(W, acY)
  ctx.stroke()
  ctx.setLineDash([])

  // Labels
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'left'

  // Current price label
  ctx.fillStyle = '#f59e0b'
  ctx.fillText(`现价 ${data.current_price.toFixed(2)}`, 4, cpY - 3)

  // Avg cost label
  ctx.fillStyle = '#8b5cf6'
  ctx.fillText(`成本 ${data.avg_cost.toFixed(2)}`, 4, acY + 12)

  // Top labels: profit ratio
  ctx.fillStyle = '#22c55e'
  ctx.textAlign = 'left'
  ctx.font = '11px sans-serif'
  ctx.fillText(`获利 ${data.profit_ratio.toFixed(1)}%`, 4, 12)

  // Trapped ratio
  const trapped = 100 - data.profit_ratio
  ctx.fillStyle = '#ef4444'
  ctx.textAlign = 'right'
  ctx.fillText(`套牢 ${trapped.toFixed(1)}%`, W - 4, 12)

  // Y-axis price labels (every ~80px)
  ctx.fillStyle = '#6b7280'
  ctx.font = '9px monospace'
  ctx.textAlign = 'right'
  const labelCount = Math.floor(chartH / 60)
  for (let i = 0; i <= labelCount; i++) {
    const price = pMax - (i / labelCount) * pRange
    const y = PAD_TOP + (i / labelCount) * chartH
    ctx.fillText(price.toFixed(1), W - 2, y + 3)
  }
}

function onResize() {
  draw()
}

onMounted(() => {
  fetchChips()
  resizeObserver = new ResizeObserver(() => draw())
  if (canvasRef.value) {
    resizeObserver.observe(canvasRef.value.parentElement || canvasRef.value)
  }
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', onResize)
  resizeObserver?.disconnect()
})

// Watch for stock changes
watch(() => stockStore.currentCode, () => {
  fetchChips()
})

// Watch for kline data changes (to sync Y axis)
watch(() => stockStore.klineData, () => {
  updatePriceRangeFromKline()
  draw()
}, { deep: false })

// Re-draw on period change
watch(() => stockStore.period, () => {
  if (stockStore.period === 'daily' || stockStore.period === 'weekly' || stockStore.period === 'monthly') {
    fetchChips()
  }
})

defineExpose({ fetchChips, updatePriceRangeFromKline })
</script>

<template>
  <div class="chips-panel">
    <div class="chips-header">
      筹码
    </div>
    <canvas
      ref="canvasRef"
      class="chips-canvas"
    />
    <div
      v-if="loading"
      class="chips-loading"
    >
      加载中
    </div>
  </div>
</template>

<style scoped>
.chips-panel {
  width: 120px;
  height: 100%;
  position: relative;
  background: #181a20;
  border-left: 1px solid #2e313a;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.chips-header {
  font-size: 11px;
  color: #6b7280;
  text-align: center;
  padding: 4px 0;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.chips-canvas {
  flex: 1;
  width: 100%;
  min-height: 0;
  display: block;
}

.chips-loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #6b7280;
  font-size: 11px;
}
</style>
