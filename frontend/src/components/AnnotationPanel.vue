<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useAnnotationStore, ANNOTATION_COLORS, ANNOTATION_LABELS } from '@/stores/annotation'
import { annotationApi } from '@/api'
import type { Annotation } from '@/types/annotation'
import { createAnnotationOverlay, removeAnnotationOverlay, clearAllOverlays, getChart } from '@/overlays/annotationOverlay'
import { useStockStore } from '@/stores/stock'

interface TradePair {
  buy_date: string
  buy_price: number | null
  buy_content: string
  sell_date: string | null
  sell_price: number | null
  sell_content: string | null
  return_pct: number | null
  holding_days: number | null
  annual_pct: number | null
  status: 'closed' | 'open'
}

interface TradePairsResponse {
  pairs: TradePair[]
  summary: {
    total_trades: number
    win_count: number
    loss_count: number
    avg_return_pct: number
    win_rate: number
  }
}

const annotationStore = useAnnotationStore()
const stockStore = useStockStore()
const editorVisible = ref(false)
const editingAnnotation = ref<Annotation | null>(null)
const formType = ref<'buy' | 'sell' | 'watch' | 'review' | 'other'>('watch')
const formContent = ref('')
const formPosition = ref<'above' | 'below'>('above')
const formDate = ref('')

// HV-003: Trade pairs tab
// NV-001: Timeline tab
interface TimelineItem {
  id: string
  stock_code: string
  stock_name: string
  type: string
  content: string
  trade_date: string
}
interface TimelineResponse {
  timeline: { date: string; annotations: TimelineItem[] }[]
}
const activeTab = ref<'list' | 'trades' | 'timeline'>('list')
const tradePairsData = ref<TradePairsResponse | null>(null)
const tradePairsLoading = ref(false)
const timelineData = ref<TimelineResponse | null>(null)
const timelineLoading = ref(false)
const timelineDays = ref(30)

async function loadTradePairs() {
  const code = stockStore.currentCode
  if (!code) return
  tradePairsLoading.value = true
  try {
    const key = localStorage.getItem('stock_access_key')
    const headers: Record<string, string> = {}
    if (key) headers['Authorization'] = `Bearer ${key}`
    const resp = await fetch(`/api/annotations/trade-pairs?stock_code=${encodeURIComponent(code)}`, { headers })
    if (resp.ok) {
      tradePairsData.value = await resp.json()
    }
  } catch (e) {
    console.error('Failed to load trade pairs:', e)
  } finally {
    tradePairsLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'trades' && !tradePairsData.value) {
    loadTradePairs()
  }
})

watch(() => stockStore.currentCode, () => {
  tradePairsData.value = null
  if (activeTab.value === 'trades') {
    loadTradePairs()
  }
})

function locateTrade(pair: TradePair) {
  const chart = getChart()
  if (!chart) return
  const targetDate = pair.buy_date
  const klineItem = stockStore.klineData.find(k => {
    const d = new Date(k.timestamp)
    const dateStr = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
    return dateStr === targetDate
  })
  if (klineItem) {
    chart.scrollToTimestamp(klineItem.timestamp)
  }
}

function locateAnnotation(ann: Annotation) {
  // FE-004: scroll chart to the annotation's K-line
  const chart = getChart()
  if (!chart) return
  const klineItem = stockStore.klineData.find(k => {
    const d = new Date(k.timestamp)
    const dateStr = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
    return dateStr === ann.trade_date
  })
  if (klineItem) {
    chart.scrollToTimestamp(klineItem.timestamp)
  }
}

function openEditor(annotationId?: string, detail?: any) {
  if (annotationId) {
    const ann = annotationStore.annotations.get(annotationId)
    if (ann) {
      editingAnnotation.value = ann
      formType.value = ann.type
      formContent.value = ann.content
      formPosition.value = ann.position
      formDate.value = ann.trade_date
    }
  } else {
    editingAnnotation.value = null
    formType.value = 'watch'
    formContent.value = ''
    formPosition.value = 'above'
    // Use the K-line date from placing mode if available
    const target = annotationStore.placingTarget
    if (target) {
      formDate.value = target.tradeDate
    } else if (detail?.tradeDate) {
      formDate.value = detail.tradeDate
    } else {
      const now = new Date()
      const bj = new Date(now.getTime() + 8 * 3600 * 1000)
      formDate.value = `${bj.getUTCFullYear()}-${String(bj.getUTCMonth() + 1).padStart(2, '0')}-${String(bj.getUTCDate()).padStart(2, '0')}`
    }
  }
  editorVisible.value = true
}

function closeEditor() {
  editorVisible.value = false
  editingAnnotation.value = null
}

async function handleSave() {
  if (editingAnnotation.value) {
    await annotationStore.update(editingAnnotation.value.id, {
      type: formType.value,
      content: formContent.value,
      position: formPosition.value,
    })
  } else {
    const ann = await annotationStore.create(formDate.value, formType.value, formContent.value, formPosition.value)
    // Create overlay for the new annotation
    const klineItem = stockStore.klineData.find(k => {
      const d = new Date(k.timestamp)
      const dateStr = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`
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
  closeEditor()
}

async function handleDelete() {
  if (editingAnnotation.value) {
    removeAnnotationOverlay(editingAnnotation.value.id)
    await annotationStore.remove(editingAnnotation.value.id)
    closeEditor()
  }
}

async function handleExport() {
  const blob = await annotationApi.export(stockStore.currentCode, 'md')
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${stockStore.currentCode}_annotations.md`
  a.click()
  URL.revokeObjectURL(url)
}

async function handleBatchDelete() {
  if (confirm(`确定删除 ${stockStore.currentCode} 的全部标注吗？此操作不可恢复。`)) {
    clearAllOverlays()
    await annotationStore.batchDelete()
  }
}

const onOpenEditorEvent = (e: any) => openEditor(e.detail?.annotationId, e.detail)

onMounted(() => {
  window.addEventListener('open-annotation-editor', onOpenEditorEvent)
})

onUnmounted(() => {
  window.removeEventListener('open-annotation-editor', onOpenEditorEvent)
})
</script>

<template>
  <div class="annotation-panel">
    <!-- Tab Switcher -->
    <div class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'list' }]"
        @click="activeTab = 'list'"
      >
        标注列表
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'trades' }]"
        @click="activeTab = 'trades'"
      >
        交易复盘
      </button>
    </div>

    <!-- Tab: 标注列表 -->
    <template v-if="activeTab === 'list'">
      <div class="panel-header">
        <h3>标注列表 ({{ annotationStore.visibleAnnotations.length }})</h3>
        <div class="header-actions">
          <button
            class="action-btn"
            title="新建标注"
            @click="openEditor()"
          >
            + 新建
          </button>
          <button
            class="action-btn"
            title="导出"
            @click="handleExport"
          >
            导出
          </button>
          <button
            class="action-btn danger"
            title="删除全部"
            @click="handleBatchDelete"
          >
            清空
          </button>
        </div>
      </div>
      <div class="annotation-list">
        <div
          v-for="ann in annotationStore.visibleAnnotations"
          :key="ann.id"
          class="annotation-item"
          :class="{ selected: annotationStore.selectedId === ann.id }"
          @click="locateAnnotation(ann); openEditor(ann.id)"
        >
          <div
            class="annotation-color-bar"
            :style="{ background: ANNOTATION_COLORS[ann.type] }"
          />
          <div class="annotation-body">
            <div class="annotation-meta">
              <span class="annotation-date">{{ ann.trade_date }}</span>
              <span
                class="annotation-type"
                :style="{ color: ANNOTATION_COLORS[ann.type] }"
              >
                {{ ANNOTATION_LABELS[ann.type] }}
              </span>
            </div>
            <div class="annotation-content">
              {{ ann.content }}
            </div>
          </div>
        </div>
        <div
          v-if="annotationStore.visibleAnnotations.length === 0"
          class="empty-state"
        >
          <p>暂无标注</p>
          <p class="hint">
            点击工具栏"标注"按钮，然后在K线上点击添加
          </p>
        </div>
      </div>
    </template>

    <!-- Tab: 交易复盘 -->
    <template v-if="activeTab === 'trades'">
      <div class="trade-panel">
        <div
          v-if="tradePairsLoading"
          class="empty-state"
        >
          <p>加载中...</p>
        </div>
        <div v-else-if="tradePairsData && tradePairsData.pairs.length > 0">
          <!-- Summary Card -->
          <div class="trade-summary">
            <div class="summary-item">
              <span class="summary-label">总交易</span>
              <span class="summary-value">{{ tradePairsData.summary.total_trades }}</span>
            </div>
            <div class="summary-item">
              <span class="summary-label">胜率</span>
              <span
                class="summary-value"
                :class="tradePairsData.summary.win_rate >= 50 ? 'profit' : 'loss'"
              >
                {{ tradePairsData.summary.win_rate }}%
              </span>
            </div>
            <div class="summary-item">
              <span class="summary-label">平均收益</span>
              <span
                class="summary-value"
                :class="tradePairsData.summary.avg_return_pct >= 0 ? 'profit' : 'loss'"
              >
                {{ tradePairsData.summary.avg_return_pct >= 0 ? '+' : '' }}{{ tradePairsData.summary.avg_return_pct }}%
              </span>
            </div>
          </div>
          <!-- Trade Pairs Table -->
          <div class="trade-table">
            <div class="trade-table-header">
              <span class="col-date">买入</span>
              <span class="col-price">价格</span>
              <span class="col-date">卖出</span>
              <span class="col-price">价格</span>
              <span class="col-return">收益率</span>
              <span class="col-days">天数</span>
            </div>
            <div
              v-for="(pair, idx) in tradePairsData.pairs"
              :key="idx"
              class="trade-row"
              @click="locateTrade(pair)"
            >
              <span class="col-date">{{ pair.buy_date }}</span>
              <span class="col-price">{{ pair.buy_price ? pair.buy_price.toFixed(2) : '-' }}</span>
              <span class="col-date">{{ pair.sell_date || '持仓中' }}</span>
              <span class="col-price">{{ pair.sell_price ? pair.sell_price.toFixed(2) : '-' }}</span>
              <span
                class="col-return"
                :class="pair.return_pct === null ? '' : (pair.return_pct >= 0 ? 'profit' : 'loss')"
              >
                {{ pair.return_pct !== null ? (pair.return_pct >= 0 ? '+' : '') + pair.return_pct + '%' : '-' }}
              </span>
              <span class="col-days">{{ pair.holding_days !== null ? pair.holding_days : '-' }}</span>
            </div>
          </div>
        </div>
        <div
          v-else
          class="empty-state"
        >
          <p>暂无买卖标注</p>
          <p class="hint">
            添加买入/卖出标注后可查看交易复盘
          </p>
        </div>
      </div>
    </template>
  </div>

  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="editorVisible"
        class="editor-backdrop"
        @click.self="closeEditor"
      >
        <div class="editor-panel">
          <h3>{{ editingAnnotation ? '编辑标注' : '新建标注' }}</h3>

          <div class="type-selector">
            <button
              v-for="(color, type) in ANNOTATION_COLORS"
              :key="type"
              :class="['type-btn', { active: formType === type }]"
              :style="{ borderColor: color, color }"
              @click="formType = type as any"
            >
              {{ ANNOTATION_LABELS[type as keyof typeof ANNOTATION_LABELS] }}
            </button>
          </div>

          <div class="field">
            <label>日期</label>
            <span class="date-display">{{ formDate }}</span>
          </div>

          <div class="field">
            <label>标注内容</label>
            <textarea
              v-model="formContent"
              rows="3"
              placeholder="输入你的分析/理由..."
              maxlength="500"
            />
            <span class="char-count">{{ formContent.length }}/500</span>
          </div>

          <div class="field">
            <label>显示位置</label>
            <div class="position-toggle">
              <button
                :class="{ active: formPosition === 'above' }"
                @click="formPosition = 'above'"
              >
                上方
              </button>
              <button
                :class="{ active: formPosition === 'below' }"
                @click="formPosition = 'below'"
              >
                下方
              </button>
            </div>
          </div>

          <div class="actions">
            <button
              v-if="editingAnnotation"
              class="btn-delete"
              @click="handleDelete"
            >
              删除
            </button>
            <div class="right-actions">
              <button
                class="btn-cancel"
                @click="closeEditor"
              >
                取消
              </button>
              <button
                class="btn-save"
                @click="handleSave"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.annotation-panel {
  width: 300px;
  height: 100%;
  background: #181a20;
  border-left: 1px solid #2e313a;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #2e313a;
}

.panel-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: #e4e4e7;
}

.header-actions {
  display: flex;
  gap: 4px;
}

.action-btn {
  padding: 4px 8px;
  border-radius: 4px;
  background: transparent;
  color: #9ca3af;
  border: none;
  cursor: pointer;
  font-size: 12px;
}

.action-btn:hover {
  color: #e4e4e7;
  background: #272a35;
}

.action-btn.danger:hover {
  color: #ef4444;
}

.annotation-list {
  flex: 1;
  overflow-y: auto;
}

.annotation-item {
  display: flex;
  padding: 8px 0;
  cursor: pointer;
  border-bottom: 1px solid #1e2028;
  transition: background 0.1s;
}

.annotation-item:hover {
  background: #272a35;
}

.annotation-item.selected {
  background: #272a35;
}

.annotation-color-bar {
  width: 3px;
  border-radius: 2px;
  margin: 0 8px;
  flex-shrink: 0;
}

.annotation-body {
  flex: 1;
  min-width: 0;
  padding-right: 12px;
}

.annotation-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.annotation-date {
  font-size: 11px;
  color: #6b7280;
  font-family: monospace;
}

.annotation-type {
  font-size: 11px;
  font-weight: 600;
}

.annotation-content {
  font-size: 13px;
  color: #d1d5db;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.empty-state {
  padding: 32px 16px;
  text-align: center;
  color: #6b7280;
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 8px;
}

/* Editor Modal */
.editor-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.editor-panel {
  background: #1e2028;
  border: 1px solid #2e313a;
  border-radius: 12px;
  padding: 24px;
  width: 400px;
  max-width: 90vw;
}

.editor-panel h3 {
  font-size: 16px;
  color: #e4e4e7;
  margin-bottom: 20px;
}

.type-selector {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.type-btn {
  padding: 6px 12px;
  border-radius: 6px;
  background: transparent;
  border: 2px solid;
  cursor: pointer;
  font-size: 13px;
  opacity: 0.6;
  transition: all 0.15s;
}

.type-btn:hover {
  opacity: 0.8;
}

.type-btn.active {
  opacity: 1;
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 6px;
}

.field textarea {
  width: 100%;
  padding: 8px 12px;
  background: #0f1117;
  border: 1px solid #2e313a;
  border-radius: 6px;
  color: #e4e4e7;
  font-size: 13px;
  resize: vertical;
  outline: none;
}

.field textarea:focus {
  border-color: #3b82f6;
}

.char-count {
  font-size: 11px;
  color: #6b7280;
  float: right;
  margin-top: 4px;
}

.date-display {
  font-size: 13px;
  color: #e4e4e7;
  font-family: monospace;
}

.position-toggle {
  display: flex;
  gap: 8px;
}

.position-toggle button {
  padding: 6px 16px;
  border-radius: 4px;
  background: #0f1117;
  color: #9ca3af;
  border: 1px solid #2e313a;
  cursor: pointer;
  font-size: 13px;
}

.position-toggle button.active {
  color: #3b82f6;
  border-color: #3b82f6;
}

.actions {
  display: flex;
  justify-content: space-between;
  margin-top: 20px;
}

.right-actions {
  display: flex;
  gap: 8px;
}

.btn-delete {
  padding: 8px 16px;
  border-radius: 6px;
  background: transparent;
  color: #ef4444;
  border: 1px solid #ef4444;
  cursor: pointer;
  font-size: 13px;
}

.btn-delete:hover {
  background: rgba(239, 68, 68, 0.1);
}

.btn-cancel {
  padding: 8px 16px;
  border-radius: 6px;
  background: transparent;
  color: #9ca3af;
  border: 1px solid #2e313a;
  cursor: pointer;
  font-size: 13px;
}

.btn-cancel:hover {
  color: #e4e4e7;
}

.btn-save {
  padding: 8px 16px;
  border-radius: 6px;
  background: #3b82f6;
  color: white;
  border: none;
  cursor: pointer;
  font-size: 13px;
}

.btn-save:hover {
  background: #2563eb;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

/* HV-003: Tab Bar */
.tab-bar {
  display: flex;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.tab-btn {
  flex: 1;
  padding: 10px 0;
  background: transparent;
  border: none;
  color: #6b7280;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: #9ca3af;
}

.tab-btn.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

/* HV-003: Trade Pairs View */
.trade-panel {
  flex: 1;
  overflow-y: auto;
}

.trade-summary {
  display: flex;
  padding: 12px 8px;
  gap: 4px;
  border-bottom: 1px solid #2e313a;
}

.summary-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.summary-label {
  font-size: 11px;
  color: #6b7280;
}

.summary-value {
  font-size: 16px;
  font-weight: 700;
  color: #e4e4e7;
}

.summary-value.profit {
  color: #ef4444;
}

.summary-value.loss {
  color: #22c55e;
}

.trade-table {
  display: flex;
  flex-direction: column;
}

.trade-table-header {
  display: flex;
  padding: 8px 8px;
  font-size: 11px;
  color: #6b7280;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.trade-row {
  display: flex;
  padding: 8px 8px;
  font-size: 12px;
  color: #d1d5db;
  border-bottom: 1px solid #1e2028;
  cursor: pointer;
  transition: background 0.1s;
}

.trade-row:hover {
  background: #272a35;
}

.col-date {
  flex: 1.2;
  font-family: monospace;
}

.col-price {
  flex: 1;
  text-align: right;
  font-family: monospace;
}

.col-return {
  flex: 1;
  text-align: right;
  font-weight: 600;
}

.col-days {
  flex: 0.6;
  text-align: right;
}

.col-return.profit {
  color: #ef4444;
}

.col-return.loss {
  color: #22c55e;
}
</style>
