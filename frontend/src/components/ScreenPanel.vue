<template>
  <div class="screen-panel">
    <div class="sp-header">
      <h3>📊 选股信号 v2</h3>
      <button
        class="sp-refresh"
        :disabled="loading"
        @click="load"
      >
        {{ loading ? '加载中…' : '刷新' }}
      </button>
    </div>

    <div
      v-if="error"
      class="sp-error"
    >
      {{ error }}
    </div>

    <template v-if="data">
      <div class="sp-meta">
        <span
          class="sp-badge"
          :class="'regime-' + (data.market_regime || '震荡')"
        >
          {{ data.market_regime }}市
        </span>
        <span>60日收益 {{ fmtPct(data.market_ret_60d) }}</span>
        <span class="sp-pos">建议仓位 {{ fmtPct(data.suggested_position) }}</span>
        <span class="sp-date">信号日 {{ data.date }}</span>
      </div>

      <div class="sp-count">
        候选 {{ data.n_candidates }} 只 → 取 Top {{ fmtPct(data.top_ratio) }}（{{ signals.length }} 只）
      </div>

      <div class="sp-table">
        <div class="sp-row sp-head">
          <span>代码</span><span>价格</span><span>得分</span><span>振幅</span><span>20日强度</span><span>换手</span>
        </div>
        <div
          v-for="s in visibleSignals"
          :key="s.stock_code"
          class="sp-row"
          :class="{ selected: s.stock_code === selectedCode }"
          @click="selectStock(s.stock_code)"
        >
          <span class="sp-code">{{ s.stock_code }}</span>
          <span>¥{{ s.close.toFixed(2) }}</span>
          <span class="sp-score">{{ s.score.toFixed(2) }}</span>
          <span>{{ fmtNum(s.factors?.V2_amp) }}</span>
          <span>{{ fmtNum(s.factors?.M1_rps20) }}</span>
          <span>{{ fmtNum(s.factors?.S5_vol_turn) }}</span>
        </div>
      </div>
      <div
        v-if="signals.length > 30"
        class="sp-more"
      >
        显示前 30/{{ signals.length }} 只
        <button
          v-if="!showAll"
          @click="showAll = true"
        >
          显示全部
        </button>
      </div>
    </template>

    <div
      v-else-if="!loading"
      class="sp-empty"
    >
      暂无信号数据，请先运行 signals_v2.py
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { screenV2Api, type ScreenV2Response } from '@/api'
import { useStockStore } from '@/stores/stock'

const data = ref<ScreenV2Response | null>(null)
const loading = ref(false)
const error = ref('')
const showAll = ref(false)
const selectedCode = ref('')
const stockStore = useStockStore()

const signals = computed(() => data.value?.signals || [])
const visibleSignals = computed(() => (showAll.value ? signals.value : signals.value.slice(0, 30)))

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await screenV2Api.latest()
    if (!data.value?.ok) error.value = data.value?.message || '加载失败'
  } catch (e: any) {
    error.value = '请求失败: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}

function selectStock(code: string) {
  selectedCode.value = code
  stockStore.selectStock(code.replace(/^(sh|sz|bj)/, ''))
}
function fmtPct(v?: number) {
  return v === undefined ? '-' : (v * 100).toFixed(0) + '%'
}
function fmtNum(v?: number | null) {
  return v === undefined || v === null ? '-' : Number(v).toFixed(3)
}

onMounted(load)
</script>

<style scoped>
.screen-panel { padding: 10px; font-size: 12px; }
.sp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sp-header h3 { margin: 0; font-size: 14px; }
.sp-refresh { background: #4f6ef7; color: #fff; border: none; border-radius: 4px; padding: 4px 10px; cursor: pointer; }
.sp-error { color: #e05; margin: 8px 0; }
.sp-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }
.sp-badge { padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.regime-牛 { background: #e33; color: #fff; }
.regime-熊 { background: #0a6; color: #fff; }
.regime-震荡 { background: #fa0; color: #fff; }
.sp-pos { font-weight: 600; color: #4f6ef7; }
.sp-date { color: #888; }
.sp-count { color: #666; margin-bottom: 6px; }
.sp-table { border: 1px solid #333; border-radius: 6px; overflow: hidden; }
.sp-row { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr 1fr 1fr; padding: 5px 8px; border-bottom: 1px solid #2a2a2a; cursor: pointer; }
.sp-row:hover { background: #1a1a2e; }
.sp-row.selected { background: #25355e; }
.sp-head { background: #1a1a1a; font-weight: 600; cursor: default; }
.sp-code { font-family: monospace; }
.sp-score { color: #4f6ef7; font-weight: 600; }
.sp-more { margin-top: 6px; color: #888; }
.sp-more button { background: none; color: #4f6ef7; border: none; cursor: pointer; }
.sp-empty { color: #888; padding: 20px; text-align: center; }
</style>
