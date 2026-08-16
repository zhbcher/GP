<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'
import { formatAmount, formatPct, formatNumber, upDownClass } from '@/utils/format'
import type { FinancePeriod } from '@/types'

const infoStore = useInfoStore()

// 最近4期
const periods = computed<FinancePeriod[]>(() => (infoStore.finance?.indicators ?? []).slice(0, 4))
const dividends = computed(() => infoStore.finance?.dividends ?? [])

function yoyArrow(val?: number | null): string {
  if (val == null) return ''
  if (val > 0) return '↑'
  if (val < 0) return '↓'
  return ''
}
</script>

<template>
  <div class="finance-tab">
    <section class="block">
      <h4 class="block-title">
        核心指标（最近4期）
      </h4>
      <div
        v-if="infoStore.financeLoading"
        class="loading"
      >
        加载中...
      </div>
      <div
        v-else-if="periods.length"
        class="table-wrap"
      >
        <table class="fin-table">
          <thead>
            <tr>
              <th class="row-label">
                报告期
              </th>
              <th
                v-for="p in periods"
                :key="p.period"
                class="num-col"
              >
                {{ p.period || '--' }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td class="row-label">
                营收
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                <div>{{ formatAmount(p.revenue) }}</div>
                <div
                  v-if="p.revenue_yoy != null"
                  class="yoy"
                  :class="upDownClass(p.revenue_yoy)"
                >
                  {{ yoyArrow(p.revenue_yoy) }}{{ formatPct(Math.abs(p.revenue_yoy)) }}
                </div>
              </td>
            </tr>
            <tr>
              <td class="row-label">
                净利
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                <div>{{ formatAmount(p.net_profit) }}</div>
                <div
                  v-if="p.net_profit_yoy != null"
                  class="yoy"
                  :class="upDownClass(p.net_profit_yoy)"
                >
                  {{ yoyArrow(p.net_profit_yoy) }}{{ formatPct(Math.abs(p.net_profit_yoy)) }}
                </div>
              </td>
            </tr>
            <tr>
              <td class="row-label">
                ROE
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                {{ formatPct(p.roe) }}
              </td>
            </tr>
            <tr>
              <td class="row-label">
                毛利率
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                {{ formatPct(p.gross_margin) }}
              </td>
            </tr>
            <tr>
              <td class="row-label">
                负债率
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                {{ formatPct(p.debt_ratio) }}
              </td>
            </tr>
            <tr>
              <td class="row-label">
                EPS
              </td>
              <td
                v-for="(p, i) in periods"
                :key="i"
                class="num-col"
              >
                {{ formatNumber(p.eps) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-else
        class="empty"
      >
        暂无数据
      </div>
    </section>

    <section class="block">
      <h4 class="block-title">
        分红历史
      </h4>
      <div
        v-if="infoStore.financeLoading"
        class="loading"
      >
        加载中...
      </div>
      <div
        v-else-if="dividends.length"
        class="dividend-list"
      >
        <div
          v-for="(d, i) in dividends"
          :key="i"
          class="dividend-row"
        >
          <span class="div-year">{{ d.year || '--' }}</span>
          <span class="div-plan">{{ d.plan || '--' }}</span>
          <span
            v-if="d.ex_date"
            class="div-date"
          >{{ d.ex_date }}</span>
        </div>
      </div>
      <div
        v-else
        class="empty"
      >
        暂无数据
      </div>
    </section>
  </div>
</template>

<style scoped>
.finance-tab {
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

.table-wrap {
  overflow-x: auto;
  border: 1px solid #30363d;
  border-radius: 6px;
}

.fin-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.fin-table th,
.fin-table td {
  padding: 6px 6px;
  border-bottom: 1px solid #21262d;
  text-align: right;
  white-space: nowrap;
}

.fin-table thead th {
  background: #0d1117;
  color: #8b949e;
  font-weight: 600;
}

.fin-table tbody tr:last-child td {
  border-bottom: none;
}

.row-label {
  text-align: left !important;
  color: #8b949e;
  position: sticky;
  left: 0;
  background: #161b22;
}

thead .row-label {
  background: #0d1117 !important;
}

.num-col {
  color: #e6edf3;
  font-family: monospace;
  min-width: 62px;
}

.yoy {
  font-size: 10px;
  margin-top: 1px;
}

.up { color: #f85149; }
.down { color: #3fb950; }
.flat { color: #8b949e; }

.dividend-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dividend-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 4px;
  font-size: 12px;
}

.div-year {
  color: #8b949e;
  font-family: monospace;
  min-width: 44px;
}

.div-plan {
  color: #e6edf3;
  flex: 1;
}

.div-date {
  color: #8b949e;
  font-family: monospace;
  font-size: 11px;
}
</style>
