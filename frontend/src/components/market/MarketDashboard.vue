<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useMarketStore } from '@/stores/market'
import { useWatchlistStore } from '@/stores/watchlist'
import { formatAmount, formatPct, formatSignedPct, upDownClass } from '@/utils/format'

const emit = defineEmits<{ (e: 'back'): void }>()

const marketStore = useMarketStore()
const watchlistStore = useWatchlistStore()

// 自选股代码集合，用于命中高亮
const watchCodes = computed(() => new Set(watchlistStore.allStocks.map(s => s.stock_code)))
function isWatch(code: string): boolean {
  return watchCodes.value.has(code)
}

const northNet = computed(() => marketStore.northFlow?.net_inflow ?? null)

onMounted(() => {
  marketStore.loadAll()
})
</script>

<template>
  <div class="market-dashboard">
    <header class="dash-header">
      <div class="header-left">
        <button class="back-btn" @click="emit('back')">← 返回</button>
        <h2 class="dash-title">市场情绪看板</h2>
      </div>
      <div class="header-right">
        <span v-if="marketStore.updatedAt" class="updated">最后更新 {{ marketStore.updatedAt }}</span>
        <button class="refresh-btn" :disabled="marketStore.loading" @click="marketStore.loadAll()">
          {{ marketStore.loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </header>

    <div class="dash-grid">
      <!-- 涨停池 -->
      <section class="card">
        <h3 class="card-title">涨停池 <span class="count">({{ marketStore.limitUp.length }})</span></h3>
        <div class="card-body">
          <div v-if="marketStore.limitUp.length" class="list">
            <div
              v-for="item in marketStore.limitUp"
              :key="item.code"
              class="list-row"
              :class="{ hit: isWatch(item.code) }"
            >
              <span class="row-name">
                {{ item.name }}
                <span class="row-code">{{ item.code }}</span>
                <span v-if="item.continuous && item.continuous > 1" class="lianban">{{ item.continuous }}连板</span>
              </span>
              <span v-if="item.reason" class="row-reason">{{ item.reason }}</span>
              <span class="row-pct up">{{ formatSignedPct(item.change_pct) }}</span>
            </div>
          </div>
          <div v-else class="empty">暂无数据</div>
        </div>
      </section>

      <!-- 北向资金 -->
      <section class="card">
        <h3 class="card-title">北向资金</h3>
        <div class="card-body">
          <div v-if="marketStore.northFlow" class="north-block">
            <div class="north-main">
              <span class="north-label">今日净流入</span>
              <span class="north-num" :class="upDownClass(northNet)">{{ formatAmount(northNet) }}</span>
            </div>
            <div class="north-sub">
              <div class="north-cell">
                <span class="ns-label">沪股通</span>
                <span class="ns-num" :class="upDownClass(marketStore.northFlow.hgt)">
                  {{ formatAmount(marketStore.northFlow.hgt) }}
                </span>
              </div>
              <div class="north-cell">
                <span class="ns-label">深股通</span>
                <span class="ns-num" :class="upDownClass(marketStore.northFlow.sgt)">
                  {{ formatAmount(marketStore.northFlow.sgt) }}
                </span>
              </div>
            </div>
          </div>
          <div v-else class="empty">暂无数据</div>
        </div>
      </section>

      <!-- 龙虎榜 -->
      <section class="card">
        <h3 class="card-title">龙虎榜 <span class="count">({{ marketStore.dragonTiger.length }})</span></h3>
        <div class="card-body">
          <div v-if="marketStore.dragonTiger.length" class="list">
            <div
              v-for="item in marketStore.dragonTiger"
              :key="item.code"
              class="list-row"
              :class="{ hit: isWatch(item.code) }"
            >
              <span class="row-name">
                {{ item.name }}
                <span class="row-code">{{ item.code }}</span>
              </span>
              <span v-if="item.reason" class="row-reason">{{ item.reason }}</span>
              <span class="row-pct" :class="upDownClass(item.net_buy)">净{{ formatAmount(item.net_buy) }}</span>
            </div>
          </div>
          <div v-else class="empty">暂无数据</div>
        </div>
      </section>

      <!-- 板块排行 -->
      <section class="card">
        <h3 class="card-title">板块排行</h3>
        <div class="card-body">
          <div v-if="marketStore.sectors.length" class="list">
            <div v-for="(item, i) in marketStore.sectors" :key="item.name" class="list-row">
              <span class="rank-num">{{ i + 1 }}</span>
              <span class="row-name">{{ item.name }}</span>
              <span v-if="item.lead_stock" class="row-reason">领涨 {{ item.lead_stock }}</span>
              <span class="row-pct" :class="upDownClass(item.change_pct)">
                {{ formatSignedPct(item.change_pct) }}
              </span>
            </div>
          </div>
          <div v-else class="empty">暂无数据</div>
        </div>
      </section>

      <!-- 热度榜 -->
      <section class="card">
        <h3 class="card-title">热度榜</h3>
        <div class="card-body">
          <div v-if="marketStore.hotRank.length" class="list">
            <div
              v-for="item in marketStore.hotRank"
              :key="item.code"
              class="list-row"
              :class="{ hit: isWatch(item.code) }"
            >
              <span class="rank-num">{{ item.rank ?? '-' }}</span>
              <span class="row-name">
                {{ item.name }}
                <span class="row-code">{{ item.code }}</span>
              </span>
              <span class="row-pct" :class="upDownClass(item.change_pct)">
                {{ formatSignedPct(item.change_pct) }}
              </span>
            </div>
          </div>
          <div v-else class="empty">暂无数据</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.market-dashboard {
  position: fixed;
  inset: 0;
  z-index: 1500;
  background: #0d1117;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 20px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.back-btn {
  padding: 6px 12px;
  border-radius: 6px;
  background: transparent;
  border: 1px solid #30363d;
  color: #e6edf3;
  font-size: 13px;
  cursor: pointer;
}

.back-btn:hover {
  background: #21262d;
}

.dash-title {
  font-size: 16px;
  font-weight: 600;
  color: #e6edf3;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.updated {
  font-size: 12px;
  color: #8b949e;
}

.refresh-btn {
  padding: 6px 14px;
  border-radius: 6px;
  background: #238636;
  border: none;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: #2ea043;
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.dash-grid {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  align-content: start;
}

.card {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.card-title {
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 600;
  color: #e6edf3;
  border-bottom: 1px solid #30363d;
}

.card-title .count {
  color: #8b949e;
  font-weight: 400;
  font-size: 12px;
}

.card-body {
  padding: 8px;
  overflow-y: auto;
  max-height: 320px;
}

.list {
  display: flex;
  flex-direction: column;
}

.list-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 5px;
  font-size: 12px;
}

.list-row:hover {
  background: #21262d;
}

/* 自选股命中高亮 */
.list-row.hit {
  background: rgba(248, 81, 73, 0.12);
  border: 1px solid rgba(248, 81, 73, 0.35);
}

.rank-num {
  width: 18px;
  text-align: center;
  color: #8b949e;
  font-family: monospace;
  flex-shrink: 0;
}

.row-name {
  color: #e6edf3;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.row-code {
  color: #8b949e;
  font-family: monospace;
  font-size: 11px;
}

.lianban {
  padding: 0 4px;
  border-radius: 3px;
  background: rgba(248, 81, 73, 0.15);
  color: #f85149;
  font-size: 10px;
}

.row-reason {
  flex: 1;
  color: #8b949e;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-pct {
  font-family: monospace;
  font-weight: 600;
  flex-shrink: 0;
  margin-left: auto;
}

.empty {
  padding: 24px;
  text-align: center;
  color: #8b949e;
  font-size: 12px;
}

/* 北向资金 */
.north-block {
  padding: 8px;
}

.north-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 12px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  margin-bottom: 10px;
}

.north-label {
  font-size: 12px;
  color: #8b949e;
}

.north-num {
  font-size: 24px;
  font-weight: 700;
  font-family: monospace;
}

.north-sub {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.north-cell {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  font-size: 12px;
}

.ns-label {
  color: #8b949e;
}

.ns-num {
  font-family: monospace;
  font-weight: 600;
}

.up { color: #f85149; }
.down { color: #3fb950; }
.flat { color: #8b949e; }
</style>
