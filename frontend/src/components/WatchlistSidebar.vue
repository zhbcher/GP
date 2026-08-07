<script setup lang="ts">
import { ref, computed } from 'vue'
import { useWatchlistStore } from '@/stores/watchlist'
import { watchlistApi, screenApi } from '@/api'
import PositionAlertPanel from './PositionAlertPanel.vue'

const watchlistStore = useWatchlistStore()
const activeGroup = ref<number | null>(null)

// NV-002: batch import
const showImportModal = ref(false)
const importText = ref('')
const importing = ref(false)
const importResult = ref<{ imported: { code: string; name: string }[]; skipped: string[]; not_found: string[] } | null>(null)

function openImportModal() {
  showImportModal.value = true
  importText.value = ''
  importResult.value = null
}

function parseImportText(): string[] {
  return importText.value
    .split(/[\n,，;；\s]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

async function doImport() {
  const codes = parseImportText()
  if (codes.length === 0) return
  importing.value = true
  try {
    importResult.value = await watchlistApi.importCodes(codes)
    await watchlistStore.load()
  } catch (e: any) {
    importResult.value = { imported: [], skipped: [], not_found: [], ...(importResult.value || {}) }
    importResult.value = { imported: [], skipped: [], not_found: [e.response?.data?.detail || '导入失败'] }
  } finally {
    importing.value = false
  }
}

// FE-003: drag-and-drop reorder
const dragIndex = ref<number | null>(null)

// MV-002: 条件筛选
interface ConditionRow {
  type: string
  days: number | null
  operator: string
  value: number | null
  ma_period: number | null
  multiplier: number | null
}

const showFilterPanel = ref(false)
const filterConditions = ref<ConditionRow[]>([])
const filteredCodes = ref<Set<string> | null>(null)  // null = no filter active
const filtering = ref(false)
const filterError = ref('')

const conditionTypeOptions = [
  { label: '近N日涨幅', value: 'return_pct' },
  { label: '站上均线', value: 'above_ma' },
  { label: 'MACD金叉', value: 'macd_golden_cross' },
  { label: '成交量放大', value: 'volume_surge' },
]

const operatorOptions = ['>', '<', '>=', '<=', '==']

function addCondition() {
  filterConditions.value.push({
    type: 'return_pct',
    days: 5,
    operator: '>',
    value: 5,
    ma_period: 20,
    multiplier: 2,
  })
}

function removeCondition(idx: number) {
  filterConditions.value.splice(idx, 1)
}

async function runScreen() {
  if (filterConditions.value.length === 0) return
  filtering.value = true
  filterError.value = ''
  try {
    const payload = filterConditions.value.map(c => {
      const obj: Record<string, any> = { type: c.type }
      if (c.type === 'return_pct') {
        obj.days = c.days
        obj.operator = c.operator
        obj.value = c.value
      } else if (c.type === 'above_ma') {
        obj.ma_period = c.ma_period
      } else if (c.type === 'volume_surge') {
        obj.days = c.days
        obj.multiplier = c.multiplier
      }
      return obj
    })
    const res = await screenApi.screen(payload)
    filteredCodes.value = new Set(res.results.map((r: any) => r.stock_code))
  } catch (e: any) {
    filterError.value = e.response?.data?.detail || '筛选失败'
    filteredCodes.value = null
  } finally {
    filtering.value = false
  }
}

function clearFilter() {
  filteredCodes.value = null
  filterConditions.value = []
  filterError.value = ''
}

const isFiltering = computed(() => filteredCodes.value !== null)

const filteredStocksFlat = computed(() => {
  const all = watchlistStore.allStocks
  if (!isFiltering.value || !filteredCodes.value) return all
  return all.filter(s => filteredCodes.value!.has(s.stock_code))
})

const displayGroups = computed(() => {
  // When filtering, flatten and show as a single list
  if (isFiltering.value) {
    return [{ id: 0, name: `筛选结果 (${filteredStocksFlat.value.length}只)`, stocks: filteredStocksFlat.value }]
  }

  if (activeGroup.value === null) {
    const result = watchlistStore.groups.map(g => ({ id: g.id, name: g.name, stocks: g.stocks }))
    if (watchlistStore.ungrouped.length > 0) {
      result.push({ id: 0, name: '未分组', stocks: watchlistStore.ungrouped })
    }
    return result
  } else if (activeGroup.value === 0) {
    return [{ id: 0, name: '未分组', stocks: watchlistStore.ungrouped }]
  } else {
    const g = watchlistStore.groups.find(g => g.id === activeGroup.value)
    return g ? [{ id: g.id, name: g.name, stocks: g.stocks }] : []
  }
})

async function selectStock(code: string, name: string) {
  window.dispatchEvent(new CustomEvent('select-stock', { detail: { code, name } }))
}

async function deleteStock(id: number, event: Event) {
  event.stopPropagation()
  await watchlistStore.removeStock(id)
}

function onDragStart(index: number) {
  dragIndex.value = index
}

async function onDrop(targetIndex: number) {
  if (dragIndex.value === null || dragIndex.value === targetIndex) return
  const stocks = watchlistStore.allStocks
  const dragged = stocks[dragIndex.value]
  const target = stocks[targetIndex]
  if (!dragged || !target) return
  // Swap sort_order
  await watchlistApi.update(dragged.id, { sort_order: target.sort_order })
  await watchlistApi.update(target.id, { sort_order: dragged.sort_order })
  dragIndex.value = null
  await watchlistStore.load()
}

function formatPrice(price: number): string {
  return price > 0 ? price.toFixed(2) : '--'
}

function formatChange(pct: number): string {
  if (pct === 0) return '0.00%'
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

function changeColor(pct: number): string {
  if (pct > 0) return 'text-up'
  if (pct < 0) return 'text-down'
  return 'text-flat'
}
</script>

<template>
  <div class="watchlist-sidebar">
    <div class="sidebar-header">
      <h3>自选股</h3>
      <div class="header-actions">
        <button
          class="import-btn"
          @click="openImportModal"
          title="批量导入"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a.5.5 0 0 1 .5.5v5.793l1.146-1.147a.5.5 0 0 1 .708.708l-2 2a.5.5 0 0 1-.708 0l-2-2a.5.5 0 1 1 .708-.708L7.5 7.293V1.5A.5.5 0 0 1 8 1z"/>
            <path d="M3 11.5a.5.5 0 0 1 .5-.5h9a.5.5 0 0 1 0 1h-9a.5.5 0 0 1-.5-.5z"/>
            <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h11A1.5 1.5 0 0 1 15 3.5v9a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 12.5v-9zm1.5-.5a.5.5 0 0 0-.5.5v9a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5v-9a.5.5 0 0 0-.5-.5h-11z"/>
          </svg>
        </button>
        <button
          class="filter-toggle-btn"
          :class="{ active: showFilterPanel || isFiltering }"
          @click="showFilterPanel = !showFilterPanel"
          title="条件筛选"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M1.5 1.5a.5.5 0 0 1 .5-.5h12a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-.146.354L10 7.707V14.5a.5.5 0 0 1-.853.354l-3-3A.5.5 0 0 1 6 11.5V7.707L1.646 3.854A.5.5 0 0 1 1.5 3.5v-2z"/>
          </svg>
          <span v-if="isFiltering" class="filter-badge">筛选中</span>
        </button>
      </div>
    </div>

    <!-- Filter Panel -->
    <div v-if="showFilterPanel" class="filter-panel">
      <div class="filter-panel-header">
        <span>条件筛选</span>
        <button class="filter-close-btn" @click="showFilterPanel = false">×</button>
      </div>

      <div v-if="filterConditions.length === 0" class="filter-empty">
        <button class="add-condition-btn" @click="addCondition">+ 添加条件</button>
      </div>

      <div v-for="(cond, idx) in filterConditions" :key="idx" class="condition-row">
        <select v-model="cond.type" class="cond-select">
          <option v-for="opt in conditionTypeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>

        <template v-if="cond.type === 'return_pct'">
          <span class="cond-label">近</span>
          <input v-model.number="cond.days" type="number" min="1" class="cond-input-sm" />
          <span class="cond-label">日涨幅</span>
          <select v-model="cond.operator" class="cond-select-sm">
            <option v-for="op in operatorOptions" :key="op" :value="op">{{ op }}</option>
          </select>
          <input v-model.number="cond.value" type="number" step="0.1" class="cond-input-sm" />
          <span class="cond-label">%</span>
        </template>

        <template v-else-if="cond.type === 'above_ma'">
          <span class="cond-label">站上 MA</span>
          <input v-model.number="cond.ma_period" type="number" min="1" class="cond-input-sm" />
        </template>

        <template v-else-if="cond.type === 'macd_golden_cross'">
          <span class="cond-label">DIF上穿DEA</span>
        </template>

        <template v-else-if="cond.type === 'volume_surge'">
          <span class="cond-label">近</span>
          <input v-model.number="cond.days" type="number" min="1" class="cond-input-sm" />
          <span class="cond-label">日均量</span>
          <input v-model.number="cond.multiplier" type="number" step="0.1" class="cond-input-sm" />
          <span class="cond-label">倍</span>
        </template>

        <button class="remove-cond-btn" @click="removeCondition(idx)">×</button>
      </div>

      <div class="filter-actions">
        <button class="add-condition-btn" @click="addCondition">+ 添加条件</button>
        <button class="run-screen-btn" :disabled="filtering || filterConditions.length === 0" @click="runScreen">
          {{ filtering ? '筛选中...' : '执行筛选' }}
        </button>
      </div>

      <div v-if="filterError" class="filter-error">{{ filterError }}</div>
    </div>

    <!-- Filter status bar -->
    <div v-if="isFiltering" class="filter-status-bar">
      <span>筛选中: {{ filteredStocksFlat.value?.length ?? filteredStocksFlat.length }}只</span>
      <button class="clear-filter-btn" @click="clearFilter">清除筛选</button>
    </div>

    <div v-if="!isFiltering" class="group-tabs">
      <button
        :class="['group-tab', { active: activeGroup === null }]"
        @click="activeGroup = null"
      >
        全部
      </button>
      <button
        v-for="g in watchlistStore.groups"
        :key="g.id"
        :class="['group-tab', { active: activeGroup === g.id }]"
        @click="activeGroup = g.id === activeGroup ? null : g.id"
      >
        {{ g.name }}
      </button>
      <button class="group-tab add-group" @click="$emit('add-group')">+</button>
    </div>

    <div class="stock-list">
      <div
        v-for="group in displayGroups"
        :key="group.id"
        class="stock-group"
      >
        <div v-if="displayGroups.length > 1 || isFiltering" class="group-label">
          {{ group.name }}
        </div>
        <div
          v-for="(stock, idx) in group.stocks"
          :key="stock.stock_code"
          class="stock-item"
          draggable="true"
          @dragstart="onDragStart(idx)"
          @dragover.prevent
          @drop="onDrop(idx)"
          @click="selectStock(stock.stock_code, stock.stock_name)"
        >
          <div class="stock-primary">
            <span class="stock-name">{{ stock.stock_name }}</span>
            <span class="stock-code">{{ stock.stock_code }}</span>
          </div>
          <div class="stock-right">
            <div class="stock-price" :class="changeColor(stock.realtime?.change_pct || 0)">
              <span class="price-value">{{ formatPrice(stock.realtime?.price || 0) }}</span>
              <span class="price-change">{{ formatChange(stock.realtime?.change_pct || 0) }}</span>
            </div>
            <button class="delete-btn" @click="deleteStock(stock.id, $event)" title="删除自选">×</button>
          </div>
        </div>
      </div>

      <div v-if="watchlistStore.allStocks.length === 0" class="empty-state">
        <p>自选股列表为空</p>
        <p class="hint">搜索股票并添加到自选</p>
      </div>

      <div v-if="isFiltering && filteredStocksFlat.length === 0" class="empty-state">
        <p>无符合条件的股票</p>
        <p class="hint">调整条件后重新筛选</p>
      </div>
    </div>

    <PositionAlertPanel />

    <!-- NV-002: Import Modal -->
    <div v-if="showImportModal" class="import-overlay" @click.self="showImportModal = false">
      <div class="import-modal">
        <div class="import-modal-header">
          <span>批量导入自选股</span>
          <button class="filter-close-btn" @click="showImportModal = false">×</button>
        </div>
        <textarea
          v-model="importText"
          class="import-textarea"
          placeholder="每行一个代码，或逗号分隔：600519, 000858, 601888&#10;支持带前缀：sh600519, sz000858"
          rows="8"
        ></textarea>
        <div class="import-modal-actions">
          <button class="import-cancel-btn" @click="showImportModal = false">取消</button>
          <button class="import-confirm-btn" :disabled="importing || parseImportText().length === 0" @click="doImport">
            {{ importing ? '导入中...' : '确认导入' }}
          </button>
        </div>
        <div v-if="importResult" class="import-result">
          <div class="import-result-row">
            <span class="result-label">✅ 导入成功</span>
            <span class="result-value">{{ importResult.imported.length }} 只</span>
          </div>
          <div v-if="importResult.imported.length" class="import-detail">
            <span v-for="s in importResult.imported" :key="s.code" class="import-tag imported">
              {{ s.name }} ({{ s.code }})
            </span>
          </div>
          <div class="import-result-row">
            <span class="result-label">⏭ 跳过（已存在）</span>
            <span class="result-value">{{ importResult.skipped.length }} 只</span>
          </div>
          <div v-if="importResult.skipped.length" class="import-detail">
            <span v-for="c in importResult.skipped" :key="c" class="import-tag skipped">{{ c }}</span>
          </div>
          <div class="import-result-row">
            <span class="result-label">❓ 未找到</span>
            <span class="result-value">{{ importResult.not_found.length }} 只</span>
          </div>
          <div v-if="importResult.not_found.length" class="import-detail">
            <span v-for="c in importResult.not_found" :key="c" class="import-tag not-found">{{ c }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.watchlist-sidebar {
  width: 260px;
  height: 100%;
  background: #181a20;
  border-right: 1px solid #2e313a;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 12px 16px;
  border-bottom: 1px solid #2e313a;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sidebar-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #e4e4e7;
  margin: 0;
}

.filter-toggle-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  background: transparent;
  border: 1px solid #2e313a;
  color: #9ca3af;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.15s;
}

.filter-toggle-btn:hover {
  color: #e4e4e7;
  border-color: #3b82f6;
}

.filter-toggle-btn.active {
  color: #3b82f6;
  border-color: #3b82f6;
}

.filter-badge {
  background: #3b82f6;
  color: #fff;
  border-radius: 2px;
  padding: 1px 4px;
  font-size: 10px;
}

.filter-panel {
  background: #1e2128;
  border-bottom: 1px solid #2e313a;
  padding: 8px 12px;
}

.filter-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: #e4e4e7;
  font-weight: 600;
}

.filter-close-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0;
}

.filter-close-btn:hover {
  color: #ef4444;
}

.filter-empty {
  text-align: center;
  padding: 8px 0;
}

.condition-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
  padding: 6px 4px;
  background: #181a20;
  border-radius: 4px;
  border: 1px solid #2e313a;
}

.cond-select {
  background: #272a35;
  border: 1px solid #2e313a;
  color: #e4e4e7;
  border-radius: 3px;
  padding: 2px 4px;
  font-size: 12px;
  flex: 1;
  min-width: 80px;
}

.cond-select-sm {
  background: #272a35;
  border: 1px solid #2e313a;
  color: #e4e4e7;
  border-radius: 3px;
  padding: 2px 4px;
  font-size: 12px;
  width: 40px;
}

.cond-input-sm {
  background: #272a35;
  border: 1px solid #2e313a;
  color: #e4e4e7;
  border-radius: 3px;
  padding: 2px 4px;
  font-size: 12px;
  width: 48px;
}

.cond-label {
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
}

.remove-cond-btn {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  font-size: 14px;
  padding: 0 2px;
  line-height: 1;
}

.remove-cond-btn:hover {
  color: #ef4444;
}

.filter-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.add-condition-btn {
  flex: 1;
  padding: 4px 8px;
  background: #272a35;
  border: 1px solid #2e313a;
  color: #9ca3af;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.add-condition-btn:hover {
  color: #3b82f6;
  border-color: #3b82f6;
}

.run-screen-btn {
  flex: 1;
  padding: 4px 8px;
  background: #3b82f6;
  border: none;
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.run-screen-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.filter-error {
  color: #ef4444;
  font-size: 11px;
  margin-top: 4px;
}

.filter-status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: rgba(59, 130, 246, 0.1);
  border-bottom: 1px solid #2e313a;
  font-size: 12px;
  color: #3b82f6;
}

.clear-filter-btn {
  background: none;
  border: 1px solid #3b82f6;
  color: #3b82f6;
  border-radius: 3px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 11px;
}

.clear-filter-btn:hover {
  background: rgba(59, 130, 246, 0.15);
}

.group-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 12px;
  border-bottom: 1px solid #2e313a;
  overflow-x: auto;
}

.group-tab {
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  background: transparent;
  color: #9ca3af;
  border: none;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.group-tab:hover {
  color: #e4e4e7;
  background: #272a35;
}

.group-tab.active {
  color: #3b82f6;
  background: #272a35;
}

.group-tab.add-group {
  color: #6b7280;
  font-weight: bold;
}

.stock-list {
  flex: 1;
  overflow-y: auto;
}

.stock-group {
  border-bottom: 1px solid #2e313a;
}

.group-label {
  padding: 6px 16px;
  font-size: 11px;
  color: #6b7280;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stock-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.1s;
}

.stock-item:hover {
  background: #272a35;
}

.stock-primary {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stock-name {
  font-size: 13px;
  color: #e4e4e7;
}

.stock-code {
  font-size: 11px;
  color: #6b7280;
  font-family: monospace;
}

.stock-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stock-price {
  text-align: right;
}

.price-value {
  font-size: 13px;
  font-weight: 600;
  font-family: monospace;
}

.price-change {
  font-size: 11px;
  display: block;
}

.delete-btn {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: transparent;
  color: #6b7280;
  border: none;
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  opacity: 0;
  transition: opacity 0.1s;
}

.stock-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.text-up { color: #ef4444; }
.text-down { color: #22c55e; }
.text-flat { color: #9ca3af; }

.empty-state {
  padding: 32px 16px;
  text-align: center;
  color: #6b7280;
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 8px;
}

  /* NV-002: Import Modal */
  .header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .import-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 4px 6px;
    border-radius: 4px;
    background: transparent;
    border: 1px solid #2e313a;
    color: #9ca3af;
    cursor: pointer;
    transition: all 0.15s;
  }
  .import-btn:hover {
    color: #e4e4e7;
    border-color: #3b82f6;
  }
  .import-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .import-modal {
    background: #1e2128;
    border: 1px solid #2e313a;
    border-radius: 8px;
    padding: 16px;
    width: 400px;
    max-width: 90vw;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .import-modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 14px;
    font-weight: 600;
    color: #e4e4e7;
  }
  .import-textarea {
    width: 100%;
    background: #181a20;
    border: 1px solid #2e313a;
    border-radius: 4px;
    color: #e4e4e7;
    padding: 10px;
    font-family: monospace;
    font-size: 13px;
    resize: vertical;
    box-sizing: border-box;
  }
  .import-textarea:focus {
    outline: none;
    border-color: #3b82f6;
  }
  .import-textarea::placeholder {
    color: #6b7280;
  }
  .import-modal-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  .import-cancel-btn {
    padding: 6px 16px;
    border-radius: 4px;
    background: transparent;
    border: 1px solid #2e313a;
    color: #9ca3af;
    cursor: pointer;
    font-size: 13px;
  }
  .import-cancel-btn:hover {
    color: #e4e4e7;
    border-color: #4b5563;
  }
  .import-confirm-btn {
    padding: 6px 16px;
    border-radius: 4px;
    background: #3b82f6;
    border: none;
    color: #fff;
    cursor: pointer;
    font-size: 13px;
  }
  .import-confirm-btn:hover:not(:disabled) {
    background: #2563eb;
  }
  .import-confirm-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .import-result {
    background: #181a20;
    border-radius: 4px;
    border: 1px solid #2e313a;
    padding: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .import-result-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 13px;
  }
  .result-label {
    color: #e4e4e7;
  }
  .result-value {
    color: #3b82f6;
    font-weight: 600;
  }
  .import-detail {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .import-tag {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 3px;
  }
  .import-tag.imported {
    background: rgba(34, 197, 94, 0.15);
    color: #22c55e;
  }
  .import-tag.skipped {
    background: rgba(156, 163, 175, 0.15);
    color: #9ca3af;
  }
  .import-tag.not-found {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }
</style>
