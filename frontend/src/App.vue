<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import TopBar from './components/TopBar.vue'
import WatchlistSidebar from './components/WatchlistSidebar.vue'
import KlineChartWrapper from './components/KlineChartWrapper.vue'
import TimelineChart from './components/TimelineChart.vue'
import DrawingToolbar from './components/DrawingToolbar.vue'
import AnnotationPanel from './components/AnnotationPanel.vue'
import InfoPanel from './components/info/InfoPanel.vue'
import JournalPanel from './components/JournalPanel.vue'
import PredictPanel from './components/PredictPanel.vue'
import MarketDashboard from './components/market/MarketDashboard.vue'
import IndustryNews from './components/news/IndustryNews.vue'
import LoginView from './components/LoginView.vue'
import CompareView from './components/CompareView.vue'
import ChipsPanel from './components/ChipsPanel.vue'
import ScreenPanel from './components/ScreenPanel.vue'
import { useWatchlistStore } from './stores/watchlist'
import { useRealtimeStore } from './stores/realtime'
import { useStockStore } from './stores/stock'
import { authApi, getAccessKey, initKeyFromUrl } from './api'
import { useUndo } from './composables/useUndo'
import type { PeriodType, AdjustType } from './types'

const sidebarOpen = ref(true)
const fullscreen = ref(false)  // FE-006
const rightPanel = ref<'annotation' | 'info' | 'journal' | 'predict' | 'screen'>('annotation')  // 右侧面板切换

// 打开预测 tab 时联动 predictStore（触发自动加载）
import { usePredictStore as usePredictStoreForTab } from '@/stores/predict'
import { useStockStore as useStockStoreForTab } from '@/stores/stock'
function openPredict() {
  const ps = usePredictStoreForTab()
  const ss = useStockStoreForTab()
  ps.visible = true
  if (ss.currentCode && !ps.result) {
    ps.load(ss.currentCode, 5)
  }
}
const showMarket = ref(false)  // 市场情绪看板全屏
const showNews = ref(false)  // 行业资讯全屏
const showChips = ref(false)  // MV-004: 筹码分布
const showCompare = ref(false)  // MV-001: 同屏对比
const chartRef = ref<InstanceType<typeof KlineChartWrapper> | null>(null)
const watchlistStore = useWatchlistStore()
const realtimeStore = useRealtimeStore()
const stockStore = useStockStore()

// ---- Auth state ----
const authEnabled = ref(false)
const authenticated = ref(false)
const authChecked = ref(false)

async function checkAuth() {
  // First: pick up ?key=*** from URL (bookmark access)
  initKeyFromUrl()
  try {
    const res = await authApi.check()
    authEnabled.value = res.auth_enabled
    if (!res.auth_enabled) {
      authenticated.value = true
    } else {
      authenticated.value = !!getAccessKey()
    }
  } catch {
    // If check fails, assume no auth
    authenticated.value = true
  }
  authChecked.value = true
}

function onAuthenticated() {
  authenticated.value = true
  initApp()
}

function onAuthExpired() {
  authenticated.value = false
}

function initApp() {
  watchlistStore.load()
  realtimeStore.connect()
}

// FE-006: keyboard shortcuts
function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return

  // Number keys 1-9: switch stock
  if (e.key >= '1' && e.key <= '9') {
    const idx = parseInt(e.key) - 1
    const stocks = watchlistStore.allStocks
    if (idx < stocks.length) {
      const s = stocks[idx]
      window.dispatchEvent(new CustomEvent('select-stock', { detail: { code: s.stock_code, name: s.stock_name } }))
    }
    return
  }

  // F11: toggle fullscreen
  if (e.key === 'F11') {
    e.preventDefault()
    fullscreen.value = !fullscreen.value
  }

  // NV-005: Ctrl+Z / Cmd+Z → undo
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    useUndo().undo()
  }
}

function onToggleChips(e: Event) {
  showChips.value = (e as CustomEvent).detail.show
}

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('auth-expired', onAuthExpired)
  window.addEventListener('toggle-chips', onToggleChips as EventListener)
  await checkAuth()
  if (authenticated.value) {
    initApp()
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('auth-expired', onAuthExpired)
  window.removeEventListener('toggle-chips', onToggleChips as EventListener)
})

function onPeriodChange(p: PeriodType) {
  if (p === 'timeline') {
    stockStore.setPeriod(p)
    return
  }
  chartRef.value?.changePeriod(p as any)
}

function onAdjustChange(a: AdjustType) {
  chartRef.value?.changeAdjust(a)
}
</script>

<template>
  <!-- Login gate -->
  <LoginView
    v-if="authChecked && !authenticated"
    @authenticated="onAuthenticated"
  />

  <template v-else-if="authChecked">
    <CompareView
      v-if="showCompare"
      @exit="showCompare = false"
    />
    <div
      v-show="!showCompare"
      class="app-layout"
      :class="{ fullscreen }"
    >
      <TopBar
        v-if="!fullscreen"
        @toggle-sidebar="sidebarOpen = !sidebarOpen"
        @period-change="onPeriodChange"
        @adjust-change="onAdjustChange"
        @open-market="showMarket = true"
        @open-news="showNews = true"
      />

      <div class="main-area">
        <WatchlistSidebar v-if="sidebarOpen && !fullscreen" />

        <div class="chart-area">
          <TimelineChart v-if="stockStore.period === 'timeline'" />
          <div
            v-show="stockStore.period !== 'timeline'"
            class="chart-with-chips"
          >
            <KlineChartWrapper ref="chartRef" />
            <ChipsPanel v-if="showChips" />
          </div>
          <DrawingToolbar
            v-if="!fullscreen"
            @open-compare="showCompare = true"
          />
        </div>

        <div
          v-if="!fullscreen"
          class="right-panel"
        >
          <div class="right-panel-tabs">
            <button
              :class="['rp-tab', { active: rightPanel === 'annotation' }]"
              @click="rightPanel = 'annotation'"
            >
              标注
            </button>
            <button
              :class="['rp-tab', { active: rightPanel === 'info' }]"
              @click="rightPanel = 'info'"
            >
              信息
            </button>
            <button
              :class="['rp-tab', { active: rightPanel === 'journal' }]"
              @click="rightPanel = 'journal'"
            >
              复盘
            </button>
            <button
              :class="['rp-tab', { active: rightPanel === 'predict' }]"
              @click="rightPanel = 'predict'; openPredict()" 
            >
              预测
            </button>
            <button
              :class="['rp-tab', { active: rightPanel === 'screen' }]"
              @click="rightPanel = 'screen'"
            >
              选股
            </button>
          </div>
          <AnnotationPanel v-show="rightPanel === 'annotation'" />
          <InfoPanel
            v-show="rightPanel === 'info'"
            :stock-code="stockStore.currentCode"
          />
          <JournalPanel v-show="rightPanel === 'journal'" />
          <PredictPanel v-show="rightPanel === 'predict'" />
          <ScreenPanel v-show="rightPanel === 'screen'" />
        </div>
      </div>

      <MarketDashboard
        v-if="showMarket"
        @back="showMarket = false"
      />
      <IndustryNews
        v-if="showNews"
        @back="showNews = false"
      />
    </div>
  </template>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  overflow: hidden;
}

.main-area {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.app-layout.fullscreen .chart-area {
  height: 100vh;
}

.chart-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chart-with-chips {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.right-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex-shrink: 0;
}

.right-panel-tabs {
  display: flex;
  background: #181a20;
  border-left: 1px solid #2e313a;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.rp-tab {
  flex: 1;
  padding: 8px 0;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: #8b949e;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.rp-tab:hover {
  color: #e6edf3;
}

.rp-tab.active {
  color: #58a6ff;
  border-bottom-color: #58a6ff;
}

.right-panel > :deep(.annotation-panel),
.right-panel > :deep(.info-panel),
.right-panel > :deep(.journal-panel) {
  flex: 1;
  min-height: 0;
}
</style>
