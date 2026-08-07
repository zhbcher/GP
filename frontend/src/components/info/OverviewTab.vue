<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'
import { formatAmount, formatPct, formatNumber, upDownClass } from '@/utils/format'

const infoStore = useInfoStore()

const valuation = computed(() => infoStore.overview?.valuation ?? null)
const fundFlow = computed(() => infoStore.overview?.fund_flow ?? null)
const concepts = computed(() => infoStore.overview?.concepts ?? [])
const unlock = computed(() => infoStore.overview?.unlock_warning ?? null)

const mainNet = computed(() => fundFlow.value?.main_net_inflow ?? null)
const mainCls = computed(() => upDownClass(mainNet.value))

const flowRows = computed(() => {
  const f = fundFlow.value
  if (!f) return []
  return [
    { label: '超大单', val: f.super_large_net },
    { label: '大单', val: f.large_net },
    { label: '中单', val: f.medium_net },
    { label: '小单', val: f.small_net },
  ]
})

const valGrid = computed(() => {
  const v = valuation.value
  if (!v) return []
  return [
    { label: 'PE', val: v.pe != null ? formatNumber(v.pe) : '--' },
    { label: 'PB', val: v.pb != null ? formatNumber(v.pb) : '--' },
    { label: '总市值', val: formatAmount(v.total_market_cap) },
    { label: '流通市值', val: formatAmount(v.float_market_cap) },
    { label: '换手率', val: formatPct(v.turnover_rate) },
  ]
})
</script>

<template>
  <div class="overview-tab">
    <!-- 解禁预警 -->
    <div v-if="unlock" class="unlock-warning">
      ⚠️ 解禁预警：{{ unlock.date || '近期' }}
      <template v-if="unlock.type"> · {{ unlock.type }}</template>
      <template v-if="unlock.ratio != null"> · 占流通股 {{ formatPct(unlock.ratio) }}</template>
    </div>

    <!-- 估值速览 -->
    <section class="block">
      <h4 class="block-title">估值速览</h4>
      <div v-if="infoStore.overviewLoading" class="loading">加载中...</div>
      <div v-else-if="valGrid.length" class="val-grid">
        <div v-for="item in valGrid" :key="item.label" class="val-cell">
          <span class="val-label">{{ item.label }}</span>
          <span class="val-num">{{ item.val }}</span>
        </div>
      </div>
      <div v-else class="empty">暂无数据</div>
    </section>

    <!-- 资金流向 -->
    <section class="block">
      <h4 class="block-title">资金流向</h4>
      <div v-if="infoStore.overviewLoading" class="loading">加载中...</div>
      <template v-else-if="fundFlow">
        <div class="main-flow">
          <span class="main-label">今日主力净流入</span>
          <span class="main-num" :class="mainCls">{{ formatAmount(mainNet) }}</span>
        </div>
        <div class="flow-rows">
          <div v-for="row in flowRows" :key="row.label" class="flow-row">
            <span class="flow-label">{{ row.label }}</span>
            <span class="flow-num" :class="upDownClass(row.val)">{{ formatAmount(row.val) }}</span>
          </div>
        </div>
      </template>
      <div v-else class="empty">暂无数据</div>
    </section>

    <!-- 概念板块 -->
    <section class="block">
      <h4 class="block-title">概念板块</h4>
      <div v-if="infoStore.overviewLoading" class="loading">加载中...</div>
      <div v-else-if="concepts.length" class="concept-tags">
        <span v-for="c in concepts" :key="c" class="concept-tag">{{ c }}</span>
      </div>
      <div v-else class="empty">暂无数据</div>
    </section>
  </div>
</template>

<style scoped>
.overview-tab {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.unlock-warning {
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(248, 81, 73, 0.12);
  border: 1px solid rgba(248, 81, 73, 0.4);
  color: #f85149;
  font-size: 12px;
  line-height: 1.4;
}

.block-title {
  font-size: 12px;
  font-weight: 600;
  color: #8b949e;
  margin-bottom: 8px;
}

.loading,
.empty {
  font-size: 12px;
  color: #8b949e;
  padding: 8px 0;
}

.val-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.val-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
}

.val-label {
  font-size: 11px;
  color: #8b949e;
}

.val-num {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
  font-family: monospace;
}

.main-flow {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 10px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  margin-bottom: 8px;
}

.main-label {
  font-size: 12px;
  color: #8b949e;
}

.main-num {
  font-size: 20px;
  font-weight: 700;
  font-family: monospace;
}

.flow-rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.flow-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 10px;
  font-size: 12px;
}

.flow-label {
  color: #8b949e;
}

.flow-num {
  font-family: monospace;
  font-weight: 500;
}

.concept-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.concept-tag {
  padding: 3px 8px;
  border-radius: 4px;
  background: #161b22;
  border: 1px solid #30363d;
  color: #e6edf3;
  font-size: 11px;
}

/* 涨跌色：红涨绿跌 */
.up { color: #f85149; }
.down { color: #3fb950; }
.flat { color: #8b949e; }
</style>
