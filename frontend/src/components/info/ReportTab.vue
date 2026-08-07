<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'
import { formatNumber } from '@/utils/format'

const infoStore = useInfoStore()
const reports = computed(() => infoStore.reports?.reports ?? [])
const consensus = computed(() => infoStore.reports?.consensus ?? null)

// 评级色块映射
const RATING_COLORS: Record<string, string> = {
  '买入': '#f85149',
  '强烈推荐': '#f85149',
  '推荐': '#f85149',
  '增持': '#f0883e',
  '谨慎增持': '#f0883e',
  '中性': '#8b949e',
  '持有': '#8b949e',
  '观望': '#8b949e',
  '减持': '#3fb950',
  '卖出': '#3fb950',
}

function ratingColor(rating?: string): string {
  if (!rating) return '#8b949e'
  return RATING_COLORS[rating] || '#8b949e'
}

function openUrl(url?: string) {
  if (url) window.open(url, '_blank', 'noopener')
}
</script>

<template>
  <div class="report-tab">
    <!-- 一致预期 -->
    <section v-if="consensus" class="consensus">
      <h4 class="block-title">一致预期 / 估值参考</h4>
      <div class="consensus-grid">
        <div class="c-cell">
          <span class="c-label">预期EPS</span>
          <span class="c-num">{{ formatNumber(consensus.eps) }}</span>
        </div>
        <div class="c-cell">
          <span class="c-label">前向PE</span>
          <span class="c-num">{{ formatNumber(consensus.forward_pe) }}</span>
        </div>
        <div class="c-cell">
          <span class="c-label">PEG</span>
          <span class="c-num">{{ formatNumber(consensus.peg) }}</span>
        </div>
      </div>
    </section>

    <section class="block">
      <h4 class="block-title">研报列表</h4>
      <div v-if="infoStore.reportsLoading" class="loading">加载中...</div>
      <template v-else-if="reports.length">
        <div
          v-for="(item, idx) in reports"
          :key="item.id ?? idx"
          class="report-item"
          :class="{ clickable: !!item.url }"
          @click="openUrl(item.url)"
        >
          <div class="report-title">{{ item.title }}</div>
          <div class="report-meta">
            <span v-if="item.org" class="report-org">{{ item.org }}</span>
            <span v-if="item.rating" class="rating-badge" :style="{ background: ratingColor(item.rating) }">
              {{ item.rating }}
            </span>
            <span v-if="item.date" class="report-date">{{ item.date }}</span>
          </div>
        </div>
      </template>
      <div v-else class="empty">暂无数据</div>
    </section>
  </div>
</template>

<style scoped>
.report-tab {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.consensus-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.c-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
}

.c-label {
  font-size: 11px;
  color: #8b949e;
}

.c-num {
  font-size: 14px;
  font-weight: 600;
  color: #e6edf3;
  font-family: monospace;
}

.report-item {
  padding: 10px 4px;
  border-bottom: 1px solid #21262d;
}

.report-item.clickable {
  cursor: pointer;
}

.report-item.clickable:hover .report-title {
  color: #58a6ff;
}

.report-title {
  font-size: 13px;
  color: #e6edf3;
  line-height: 1.4;
  margin-bottom: 6px;
  transition: color 0.1s;
}

.report-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.report-org {
  color: #8b949e;
}

.rating-badge {
  padding: 1px 6px;
  border-radius: 3px;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
}

.report-date {
  color: #8b949e;
  font-family: monospace;
}
</style>
