<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { usePositionStore } from '@/stores/position'
import { useAlertStore } from '@/stores/alert'
import { useStockStore } from '@/stores/stock'
import { useRealtimeStore } from '@/stores/realtime'

const positionStore = usePositionStore()
const alertStore = useAlertStore()
const stockStore = useStockStore()
const realtimeStore = useRealtimeStore()

const activeTab = ref<'position' | 'alert'>('position')

// Position form
const showPosForm = ref(false)
const posForm = ref({ cost_price: '', quantity: '', buy_date: '', note: '' })

// Alert form
const showAlertForm = ref(false)
const alertForm = ref({
  alert_type: 'price' as 'price' | 'change_pct' | 'volume',
  target_price: '',
  direction: 'above' as 'above' | 'below',
  pct_threshold: '',
  volume_ratio: '',
  volume_days: '5',
})

onMounted(() => {
  positionStore.load()
  positionStore.loadSummary()
  alertStore.load()
})

const currentPositions = computed(() =>
  positionStore.positions.filter(p => p.stock_code === stockStore.currentCode)
)

const currentAlerts = computed(() =>
  alertStore.alerts.filter(a => a.stock_code === stockStore.currentCode)
)

/** Current price: realtime quote first, fallback to latest kline close */
function positionPrice(pos: any): number {
  const q = realtimeStore.quotes.get(pos.stock_code)
  if (q?.price) return q.price
  if (pos.stock_code === stockStore.currentCode && stockStore.klineData.length > 0) {
    return stockStore.klineData[stockStore.klineData.length - 1].close
  }
  return 0
}

function isRealtimePrice(pos: any): boolean {
  const q = realtimeStore.quotes.get(pos.stock_code)
  return !!(q?.price)
}

function profitPct(pos: any): number {
  const price = positionPrice(pos)
  if (!price || !pos.cost_price) return 0
  return (price - pos.cost_price) / pos.cost_price * 100
}

function profitAmount(pos: any): number {
  const price = positionPrice(pos)
  if (!price || !pos.cost_price) return 0
  return (price - pos.cost_price) * pos.quantity
}

function marketValue(pos: any): number {
  const price = positionPrice(pos)
  if (!price) return 0
  return price * pos.quantity
}

const totalMarketValue = computed(() =>
  currentPositions.value.reduce((s, p) => s + marketValue(p), 0)
)
const totalCost = computed(() =>
  currentPositions.value.reduce((s, p) => s + p.cost_price * p.quantity, 0)
)
const totalProfit = computed(() =>
  currentPositions.value.reduce((s, p) => s + profitAmount(p), 0)
)
const totalProfitPct = computed(() =>
  totalCost.value > 0 ? totalProfit.value / totalCost.value * 100 : 0
)

/** Format money: >=10000 show as 万 */
function fmtMoney(v: number, sign = true): string {
  const s = sign && v > 0 ? '+' : ''
  if (Math.abs(v) >= 10000) return s + (v / 10000).toFixed(2) + '万'
  return s + v.toFixed(2)
}

async function savePosition() {
  if (!posForm.value.cost_price || !posForm.value.quantity) return
  await positionStore.create({
    stock_code: stockStore.currentCode,
    stock_name: stockStore.currentName,
    cost_price: parseFloat(posForm.value.cost_price),
    quantity: parseInt(posForm.value.quantity),
    buy_date: posForm.value.buy_date,
    note: posForm.value.note,
  })
  posForm.value = { cost_price: '', quantity: '', buy_date: '', note: '' }
  showPosForm.value = false
  positionStore.loadSummary()
}

async function removePosition(id: number) {
  await positionStore.remove(id)
  positionStore.loadSummary()
}

async function saveAlert() {
  const f = alertForm.value
  if (f.alert_type === 'price' && !f.target_price) return
  if (f.alert_type === 'change_pct' && !f.pct_threshold) return
  if (f.alert_type === 'volume' && !f.volume_ratio) return

  await alertStore.create({
    stock_code: stockStore.currentCode,
    stock_name: stockStore.currentName,
    alert_type: f.alert_type,
    target_price: f.alert_type === 'price' ? parseFloat(f.target_price) : 0,
    direction: f.direction,
    pct_threshold: f.alert_type === 'change_pct' ? parseFloat(f.pct_threshold) : 0,
    volume_ratio: f.alert_type === 'volume' ? parseFloat(f.volume_ratio) : 0,
    volume_days: f.alert_type === 'volume' ? parseInt(f.volume_days) : 5,
  })
  alertForm.value = {
    alert_type: 'price',
    target_price: '',
    direction: 'above',
    pct_threshold: '',
    volume_ratio: '',
    volume_days: '5',
  }
  showAlertForm.value = false
}

const alertTypeLabels: Record<string, string> = {
  price: '目标价',
  change_pct: '涨跌幅',
  volume: '放量',
}

const alertTypeColors: Record<string, string> = {
  price: '#3b82f6',
  change_pct: '#f59e0b',
  volume: '#a855f7',
}

function alertLabel(a: any): string {
  if (a.alert_type === 'price') {
    return `${a.direction === 'above' ? '涨到' : '跌到'} ${a.target_price?.toFixed(2) ?? ''}`
  } else if (a.alert_type === 'change_pct') {
    return `${a.direction === 'above' ? '涨超' : '跌超'} ${a.pct_threshold}%`
  } else if (a.alert_type === 'volume') {
    return `${a.volume_days}日均量 × ${a.volume_ratio}`
  }
  return ''
}
</script>

<template>
  <div class="pos-alert-panel">
    <div class="panel-tabs">
      <button :class="{ active: activeTab === 'position' }" @click="activeTab = 'position'">持仓</button>
      <button :class="{ active: activeTab === 'alert' }" @click="activeTab = 'alert'">预警</button>
    </div>

    <!-- Position tab -->
    <div v-if="activeTab === 'position'" class="panel-content">
      <!-- Grand total across ALL stocks -->
      <div v-if="positionStore.summary" class="grand-total" :class="positionStore.summary.total_profit >= 0 ? 'profit-up' : 'profit-down'">
        <div class="grand-cell">
          <span class="grand-label">证券市值</span>
          <span class="grand-value">{{ fmtMoney(positionStore.summary.market_value, false) }}</span>
        </div>
        <div class="grand-divider"></div>
        <div class="grand-cell">
          <span class="grand-label">总盈亏</span>
          <span class="grand-value" :class="positionStore.summary.total_profit >= 0 ? 'text-up' : 'text-down'">
            {{ fmtMoney(positionStore.summary.total_profit) }}
            <i class="grand-pct">{{ positionStore.summary.profit_pct >= 0 ? '+' : '' }}{{ positionStore.summary.profit_pct.toFixed(2) }}%</i>
          </span>
        </div>
      </div>

      <button class="add-btn" @click="showPosForm = !showPosForm">
        {{ showPosForm ? '取消' : '+ 添加持仓' }}
      </button>

      <div v-if="showPosForm" class="form-section">
        <input v-model="posForm.cost_price" type="number" placeholder="成本价" step="0.001" />
        <input v-model="posForm.quantity" type="number" placeholder="数量(股)" step="100" />
        <input v-model="posForm.buy_date" type="date" />
        <input v-model="posForm.note" placeholder="备注" />
        <button class="save-btn" @click="savePosition">保存</button>
      </div>

      <!-- Summary bar -->
      <div v-if="currentPositions.length > 0" class="pos-summary">
        <div class="summary-item">
          <span class="summary-label">总市值</span>
          <span class="summary-value">{{ fmtMoney(totalMarketValue, false) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总盈亏</span>
          <span class="summary-value" :class="totalProfit >= 0 ? 'text-up' : 'text-down'">{{ fmtMoney(totalProfit) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">收益率</span>
          <span class="summary-value" :class="totalProfitPct >= 0 ? 'text-up' : 'text-down'">{{ totalProfitPct >= 0 ? '+' : '' }}{{ totalProfitPct.toFixed(2) }}%</span>
        </div>
      </div>

      <div v-for="pos in currentPositions" :key="pos.id" class="pos-item">
        <div class="pos-main">
          <div class="pos-row">
            <span class="pos-cost">成本 <b>{{ pos.cost_price.toFixed(3) }}</b></span>
            <span class="pos-qty">{{ pos.quantity }}股</span>
            <button class="del-btn" @click="removePosition(pos.id)">×</button>
          </div>
          <div class="pos-row">
            <span class="pos-cur">现价 <b>{{ positionPrice(pos) ? positionPrice(pos).toFixed(2) : '--' }}</b><i v-if="!isRealtimePrice(pos) && positionPrice(pos)" class="price-tag">收</i></span>
            <span class="pos-mv">市值 {{ fmtMoney(marketValue(pos), false) }}</span>
          </div>
        </div>
        <div class="pos-profit-box" :class="profitPct(pos) >= 0 ? 'text-up' : 'text-down'">
          <span class="pos-profit-amt">{{ fmtMoney(profitAmount(pos)) }}</span>
          <span class="pos-profit-pct">{{ profitPct(pos) >= 0 ? '+' : '' }}{{ profitPct(pos).toFixed(2) }}%</span>
        </div>
      </div>

      <div v-if="currentPositions.length === 0 && !showPosForm" class="empty">暂无持仓</div>
    </div>

    <!-- Alert tab -->
    <div v-if="activeTab === 'alert'" class="panel-content">
      <button class="add-btn" @click="showAlertForm = !showAlertForm">
        {{ showAlertForm ? '取消' : '+ 添加预警' }}
      </button>

      <div v-if="showAlertForm" class="form-section">
        <select v-model="alertForm.alert_type">
          <option value="price">目标价</option>
          <option value="change_pct">涨跌幅</option>
          <option value="volume">放量</option>
        </select>

        <!-- Price alert params -->
        <template v-if="alertForm.alert_type === 'price'">
          <input v-model="alertForm.target_price" type="number" placeholder="目标价" step="0.01" />
          <select v-model="alertForm.direction">
            <option value="above">涨到</option>
            <option value="below">跌到</option>
          </select>
        </template>

        <!-- Change pct alert params -->
        <template v-if="alertForm.alert_type === 'change_pct'">
          <input v-model="alertForm.pct_threshold" type="number" placeholder="涨跌幅阈值(%)" step="0.1" />
          <select v-model="alertForm.direction">
            <option value="above">涨超</option>
            <option value="below">跌超</option>
          </select>
        </template>

        <!-- Volume alert params -->
        <template v-if="alertForm.alert_type === 'volume'">
          <input v-model="alertForm.volume_days" type="number" placeholder="均量天数" step="1" />
          <input v-model="alertForm.volume_ratio" type="number" placeholder="倍数(如2.0)" step="0.1" />
        </template>

        <button class="save-btn" @click="saveAlert">保存</button>
      </div>

      <div v-for="alert in currentAlerts" :key="alert.id" class="alert-item">
        <div class="alert-info">
          <span class="alert-type-tag" :style="{ color: alertTypeColors[alert.alert_type] || '#3b82f6' }">
            {{ alertTypeLabels[alert.alert_type] || alert.alert_type }}
          </span>
          <span class="alert-desc">{{ alertLabel(alert) }}</span>
        </div>
        <span v-if="alert.triggered" class="alert-triggered">已触发</span>
        <button class="del-btn" @click="alertStore.remove(alert.id)">×</button>
      </div>

      <div v-if="currentAlerts.length === 0 && !showAlertForm" class="empty">暂无预警</div>
    </div>
  </div>
</template>

<style scoped>
.pos-alert-panel {
  border-top: 1px solid #2e313a;
  padding: 8px 12px;
}

.panel-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.panel-tabs button {
  padding: 4px 12px;
  border-radius: 4px;
  background: transparent;
  color: #9ca3af;
  border: none;
  cursor: pointer;
  font-size: 12px;
}

.panel-tabs button.active {
  color: #3b82f6;
  background: #272a35;
}

.add-btn {
  width: 100%;
  padding: 6px;
  border-radius: 4px;
  background: #272a35;
  color: #9ca3af;
  border: 1px dashed #3b82f6;
  cursor: pointer;
  font-size: 12px;
  margin-bottom: 8px;
}

.add-btn:hover { color: #3b82f6; }

.form-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

.form-section input,
.form-section select {
  padding: 6px 8px;
  background: #0f1117;
  border: 1px solid #2e313a;
  border-radius: 4px;
  color: #e4e4e7;
  font-size: 12px;
  outline: none;
}

.form-section input:focus,
.form-section select:focus { border-color: #3b82f6; }

.save-btn {
  padding: 6px;
  border-radius: 4px;
  background: #3b82f6;
  color: white;
  border: none;
  cursor: pointer;
  font-size: 12px;
}

.save-btn:hover { background: #2563eb; }

.grand-total {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 10px 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1c2434 0%, #171b26 100%);
  border: 1px solid #26304a;
  position: relative;
  overflow: hidden;
}

.grand-total::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  transition: background 0.3s;
}

.grand-total.profit-up::before { background: #ef4444; }
.grand-total.profit-down::before { background: #22c55e; }

.grand-cell {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.grand-divider {
  width: 1px;
  background: #2e313a;
  margin: 0 12px;
}

.grand-label {
  font-size: 10px;
  color: #6b7280;
  letter-spacing: 1px;
}

.grand-value {
  font-size: 16px;
  font-weight: 700;
  font-family: monospace;
  color: #e4e4e7;
  display: flex;
  align-items: baseline;
  gap: 6px;
  white-space: nowrap;
}

.grand-pct {
  font-style: normal;
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
}

.pos-summary {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  margin-bottom: 6px;
  background: #1e2028;
  border-radius: 6px;
  border-left: 3px solid #3b82f6;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.summary-label {
  font-size: 10px;
  color: #6b7280;
}

.summary-value {
  font-size: 13px;
  font-weight: 700;
  font-family: monospace;
  color: #e4e4e7;
}

.pos-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 6px;
  margin-bottom: 4px;
  border-radius: 6px;
  background: #181a20;
  border: 1px solid #1e2028;
  font-size: 12px;
  transition: border-color 0.15s, background 0.15s;
}

.pos-item:hover {
  border-color: #2e313a;
  background: #1a1c24;
}

.pos-item .del-btn {
  opacity: 0;
  transition: opacity 0.15s;
}

.pos-item:hover .del-btn {
  opacity: 1;
}

.pos-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.pos-row {
  display: flex;
  gap: 10px;
  align-items: center;
  color: #9ca3af;
}

.pos-row b {
  color: #e4e4e7;
  font-family: monospace;
  font-weight: 600;
}

.pos-cost, .pos-cur { white-space: nowrap; }

.pos-qty { color: #6b7280; }
.pos-mv { color: #6b7280; font-family: monospace; }

.price-tag {
  display: inline-block;
  font-style: normal;
  font-size: 9px;
  color: #f59e0b;
  border: 1px solid #f59e0b;
  border-radius: 3px;
  padding: 0 3px;
  margin-left: 4px;
  line-height: 1.4;
  opacity: 0.8;
}

.pos-profit-box {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  padding-right: 4px;
}

.pos-profit-amt {
  font-family: monospace;
  font-weight: 700;
  font-size: 13px;
}

.pos-profit-pct {
  font-family: monospace;
  font-size: 11px;
  opacity: 0.85;
}

.alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid #1e2028;
  font-size: 12px;
}

.alert-info {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #d1d5db;
}

.alert-type-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 5px;
  border-radius: 3px;
  background: #1e2028;
  white-space: nowrap;
}

.alert-desc {
  font-family: monospace;
  font-size: 11px;
}

.alert-triggered {
  color: #f59e0b;
  font-size: 11px;
}

.del-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.del-btn:hover { color: #ef4444; }

.empty {
  text-align: center;
  color: #6b7280;
  font-size: 12px;
  padding: 12px 0;
}

.text-up { color: #ef4444; }
.text-down { color: #22c55e; }
</style>
