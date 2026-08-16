<script setup lang="ts">
import { ref } from 'vue'
import { useStockStore } from '@/stores/stock'
import { useAnnotationStore } from '@/stores/annotation'
import { useWatchlistStore } from '@/stores/watchlist'
import { useTheme } from '@/composables/useTheme'
import type { PeriodType, AdjustType } from '@/types'
import { stockApi, backupApi } from '@/api'

const { theme, toggle: toggleTheme } = useTheme()

const stockStore = useStockStore()
const annotationStore = useAnnotationStore()
const watchlistStore = useWatchlistStore()
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const showSearch = ref(false)

const periods: { key: PeriodType; label: string }[] = [
  { key: 'timeline', label: '分时' },
  { key: '5min', label: '5分' },
  { key: '15min', label: '15分' },
  { key: '30min', label: '30分' },
  { key: '60min', label: '60分' },
  { key: 'daily', label: '日K' },
  { key: 'weekly', label: '周K' },
  { key: 'monthly', label: '月K' },
  { key: 'yearly', label: '年K' },
]

const adjusts: { key: AdjustType; label: string }[] = [
  { key: 'qfq', label: '前复权' },
  { key: 'hfq', label: '后复权' },
  { key: 'none', label: '不复权' },
]

async function onSearch() {
  if (!searchQuery.value || searchQuery.value.trim().length < 1) {
    searchResults.value = []
    showSearch.value = false
    return
  }
  try {
    searchResults.value = await stockApi.search(searchQuery.value)
    showSearch.value = searchResults.value.length > 0
  } catch (e) {
    console.error('Search failed:', e)
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    onSearch()
  }
}

async function selectStock(item: { code: string; name: string }) {
  stockStore.setStock(item.code, item.name)
  searchQuery.value = `${item.name} (${item.code})`
  showSearch.value = false
  // Dispatch event for KlineChartWrapper to load the stock
  window.dispatchEvent(new CustomEvent('select-stock', { detail: { code: item.code, name: item.name } }))
}

async function addToWatchlist(item: { code: string; name: string }) {
  try {
    await watchlistStore.addStock({ stock_code: item.code, stock_name: item.name })
  } catch (e: any) {
    // 409 = already in watchlist, ignore
    if (e?.response?.status !== 409) {
      console.error('Add to watchlist failed:', e)
    }
  }
}

function toggleAnnotationMode() {
  const newMode = annotationStore.mode === 'idle' ? 'placing' : 'idle'
  annotationStore.setMode(newMode)
}

// BE-004: backup / restore
async function downloadBackup() {
  const blob = await backupApi.download()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `stock_backup_${new Date().toISOString().slice(0, 10)}.db`
  a.click()
  URL.revokeObjectURL(url)
}

function triggerRestore() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.db'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    if (!confirm('恢复将覆盖当前所有数据，确定继续？')) return
    try {
      await backupApi.restore(file)
      alert('恢复成功，请刷新页面。')
      location.reload()
    } catch (e) {
      alert('恢复失败：' + (e as any)?.message)
    }
  }
  input.click()
}
</script>

<template>
  <div class="top-bar">
    <div class="left-section">
      <div class="search-box">
        <div class="search-input-wrapper">
          <input
            v-model="searchQuery"
            placeholder="搜索股票代码/名称..."
            @keydown.enter="onSearch"
          >
          <button
            class="search-btn"
            title="搜索"
            @click="onSearch"
          >
            🔍
          </button>
        </div>
        <Transition name="fade">
          <div
            v-if="showSearch && searchResults.length > 0"
            class="search-dropdown"
          >
            <div
              v-for="item in searchResults"
              :key="item.code"
              class="search-item"
              @mousedown.prevent="selectStock(item)"
            >
              <span class="search-code">{{ item.code }}</span>
              <span class="search-name">{{ item.name }}</span>
              <button 
                class="add-watchlist-btn" 
                :title="'加入自选'" 
                @mousedown.prevent.stop="addToWatchlist(item)"
              >
                +
              </button>
            </div>
          </div>
        </Transition>
      </div>
      <div class="stock-info">
        <span class="stock-name">{{ stockStore.currentName || '请选择股票' }}</span>
        <span class="stock-code">{{ stockStore.currentCode }}</span>
      </div>
    </div>

    <div class="center-section">
      <div class="period-tabs">
        <button
          v-for="p in periods"
          :key="p.key"
          :class="['period-btn', { active: stockStore.period === p.key }]"
          @click="$emit('period-change', p.key)"
        >
          {{ p.label }}
        </button>
      </div>
    </div>

    <div class="right-section">
      <div
        v-if="!['timeline', 'minute', '5min', '15min', '30min', '60min'].includes(stockStore.period)"
        class="adjust-tabs"
      >
        <button
          v-for="a in adjusts"
          :key="a.key"
          :class="['adjust-btn', { active: stockStore.adjust === a.key }]"
          @click="$emit('adjust-change', a.key)"
        >
          {{ a.label }}
        </button>
      </div>
      <button
        :class="['annotation-btn', { active: annotationStore.mode === 'placing' }]"
        title="标注"
        @click="toggleAnnotationMode"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
      </button>
      <button
        class="market-btn"
        title="市场情绪看板"
        @click="$emit('open-market')"
      >
        市场
      </button>
      <button
        class="market-btn"
        title="行业资讯"
        @click="$emit('open-news')"
      >
        资讯
      </button>
      <div class="backup-btns">
        <button
          class="icon-btn"
          title="备份数据"
          @click="downloadBackup"
        >
          💾
        </button>
        <button
          class="icon-btn"
          title="恢复数据"
          @click="triggerRestore"
        >
          📂
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  height: 48px;
  padding: 0 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  gap: 16px;
  flex-shrink: 0;
}

.left-section {
  display: flex;
  align-items: center;
  gap: 16px;
}

.search-box {
  position: relative;
}

.search-input-wrapper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.search-box input {
  width: 180px;
  height: 32px;
  padding: 0 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  border-radius: 6px 0 0 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.search-box input:focus {
  border-color: #3b82f6;
}

.search-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  border: none;
  border-radius: 0 6px 6px 0;
  cursor: pointer;
  font-size: 14px;
  transition: opacity 0.15s;
}

.search-btn:hover {
  opacity: 0.85;
}

.search-dropdown {
  position: absolute;
  top: 36px;
  left: 0;
  width: 280px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  box-shadow: var(--shadow-dropdown);
  z-index: 100;
}

.search-item {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  gap: 8px;
}

.search-item:hover {
  background: var(--bg-hover);
}

.search-code {
  color: var(--text-secondary);
  font-size: 12px;
  font-family: monospace;
}

.search-name {
  color: var(--text-primary);
  font-size: 13px;
  flex: 1;
}

.add-watchlist-btn {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border-color);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
  transition: all 0.1s;
}

.add-watchlist-btn:hover {
  color: #22c55e;
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.stock-info {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.stock-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.stock-code {
  font-size: 12px;
  color: var(--text-muted);
  font-family: monospace;
}

.center-section {
  display: flex;
  flex: 1;
  justify-content: center;
}

.period-tabs {
  display: flex;
  gap: 4px;
}

.period-btn {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}

.period-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.period-btn.active {
  color: var(--accent);
  background: var(--bg-hover);
}

.right-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

.adjust-tabs {
  display: flex;
  gap: 4px;
}

.adjust-btn {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  background: transparent;
  color: var(--text-secondary);
  border: none;
  cursor: pointer;
}

.adjust-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.adjust-btn.active {
  color: var(--accent);
  background: var(--bg-hover);
}

.annotation-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: all 0.15s;
}

.annotation-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.annotation-btn.active {
  color: #22c55e;
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}

.market-btn {
  padding: 0 12px;
  height: 32px;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  border: 1px solid var(--border-color);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.market-btn:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
  border-color: var(--accent);
}

.backup-btns {
  display: flex;
  gap: 4px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: transparent;
  border: 1px solid var(--border-color);
  cursor: pointer;
  font-size: 14px;
  transition: all 0.15s;
}

.icon-btn:hover {
  background: var(--bg-hover);
  border-color: var(--accent);
}
</style>
