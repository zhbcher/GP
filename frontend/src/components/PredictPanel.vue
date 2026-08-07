<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePredictStore } from '@/stores/predict'
import { useStockStore } from '@/stores/stock'
import { predictApi, type ModelAccuracy } from '@/api'

// D3: 模型准确率（回测统计，与当前股票无关，面板打开时加载）
const accuracyModels = ref<ModelAccuracy[]>([])
const accuracyLoading = ref(false)
const MODEL_LABELS: Record<string, string> = {
  technical: '技术指标', statistical: '统计模型', monte_carlo: '蒙特卡洛',
  ml: 'XGBoost', patterns: '形态识别', deep_learning: 'LSTM', ensemble: '集成',
}
async function loadAccuracy() {
  accuracyLoading.value = true
  try {
    const resp = await predictApi.accuracy()
    accuracyModels.value = resp.models || []
  } catch (e) {
    accuracyModels.value = []
  } finally {
    accuracyLoading.value = false
  }
}
onMounted(loadAccuracy)

const predictStore = usePredictStore()
const stockStore = useStockStore()

const days = ref(5)

watch(() => stockStore.currentCode, () => {
  if (predictStore.visible && stockStore.currentCode) {
    predictStore.load(stockStore.currentCode, days.value)
  }
})

function refresh() {
  if (stockStore.currentCode) {
    predictStore.load(stockStore.currentCode, days.value)
  }
}

const ensembleTrend = computed(() => {
  const e = predictStore.result?.ensemble
  if (!e || 'error' in e) return null
  return e as { trend: string; confidence: number; votes: Record<string, number>; price_target: Record<string, number> }
})

const modelVotes = computed(() => {
  const models = predictStore.result?.models
  if (!models) return []
  const items: { name: string; label: string; trend: string; confidence: number }[] = []
  const labels: Record<string, string> = {
    technical: '技术指标', statistical: '统计模型', monte_carlo: '蒙特卡洛',
    ml: 'XGBoost', patterns: '形态识别', deep_learning: 'LSTM'
  }
  for (const [key, value] of Object.entries(models)) {
    if (typeof value === 'object' && value !== null && 'trend' in (value as any)) {
      const v = value as any
      items.push({
        name: key,
        label: labels[key] || key,
        trend: v.trend === 'up' ? '↑ 看涨' : v.trend === 'down' ? '↓ 看跌' : '→ 震荡',
        confidence: v.confidence || 0
      })
    }
  }
  return items
})

const trendEmoji = computed(() => {
  const t = ensembleTrend.value?.trend
  if (t === 'up') return '📈'
  if (t === 'down') return '📉'
  return '📊'
})

const trendLabel = computed(() => {
  const t = ensembleTrend.value?.trend
  if (t === 'up') return '看涨'
  if (t === 'down') return '看跌'
  return '震荡'
})
</script>

<template>
  <div class="predict-panel">
    <div class="panel-header">
      <h3>预测分析</h3>
      <div class="header-actions">
        <select v-model="days" class="days-select">
          <option :value="5">5 天</option>
          <option :value="10">10 天</option>
          <option :value="20">20 天</option>
        </select>
        <button class="refresh-btn" :disabled="predictStore.loading" @click="refresh">
          {{ predictStore.loading ? '分析中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="predictStore.loading" class="loading">分析中，请稍候...</div>
    <div v-else-if="predictStore.error" class="error">{{ predictStore.error }}</div>
    <div v-else-if="ensembleTrend" class="predict-content">
      <!-- 综合趋势 -->
      <div class="ensemble-card">
        <div class="ensemble-icon">{{ trendEmoji }}</div>
        <div class="ensemble-info">
          <div class="ensemble-trend">
            综合趋势: <strong :class="'text-' + ensembleTrend.trend">{{ trendLabel }}</strong>
            <span class="confidence">{{ (ensembleTrend.confidence * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="ensembleTrend.price_target" class="ensemble-price">
            目标价: {{ ensembleTrend.price_target.median }} 
            ({{ ensembleTrend.price_target.range_low }} ~ {{ ensembleTrend.price_target.range_high }})
          </div>
        </div>
      </div>

      <!-- 各模型投票 -->
      <div class="model-votes">
        <h4>各模型投票</h4>
        <div v-for="item in modelVotes" :key="item.name" class="vote-item">
          <span class="vote-label">{{ item.label }}</span>
          <span :class="['vote-trend', 'text-' + (item.trend.includes('看涨') ? 'up' : item.trend.includes('看跌') ? 'down' : 'sideways')]">
            {{ item.trend }}
          </span>
          <span class="vote-confidence">{{ (item.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- D3: 模型准确率（回测） -->
      <div class="accuracy-section">
        <h4>模型准确率（回测）</h4>
        <div v-if="accuracyLoading" class="accuracy-loading">加载中…</div>
        <div v-else-if="accuracyModels.length === 0" class="accuracy-empty">样本积累中</div>
        <template v-else>
          <div v-for="m in accuracyModels" :key="m.model" class="accuracy-item">
            <span class="accuracy-label">{{ MODEL_LABELS[m.model] || m.model }}</span>
            <span class="accuracy-value" :class="{ good: m.accuracy >= 55, bad: m.accuracy < 45 }">{{ m.accuracy.toFixed(1) }}%</span>
            <span class="accuracy-samples">{{ m.samples >= 30 ? m.samples + ' 次' : '样本积累中' }}</span>
          </div>
        </template>
      </div>

      <!-- 形态识别 -->
      <div v-if="predictStore.result?.models?.patterns?.patterns?.length" class="patterns-section">
        <h4>形态识别</h4>
        <div v-for="p in predictStore.result.models.patterns.patterns" :key="p.type" class="pattern-item">
          <span class="pattern-type">{{ p.label || p.type }}</span>
          <span class="pattern-confidence">{{ (p.confidence * 100).toFixed(0) }}%</span>
        </div>
      </div>

      <!-- 支撑/阻力 -->
      <div v-if="predictStore.result?.models?.patterns?.support?.length" class="levels-section">
        <h4>关键价位</h4>
        <div class="level-row">
          <span class="level-label">阻力位</span>
          <span class="level-value">{{ predictStore.result.models.patterns.resistance?.[0]?.price }}</span>
        </div>
        <div class="level-row">
          <span class="level-label">支撑位</span>
          <span class="level-value">{{ predictStore.result.models.patterns.support?.[0]?.price }}</span>
        </div>
      </div>
    </div>
    <div v-else class="empty">
      点击"预测"按钮或切换股票开始分析
    </div>
  </div>
</template>

<style scoped>
.predict-panel { padding: 12px; font-size: 13px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.panel-header h3 { margin: 0; font-size: 14px; }
.header-actions { display: flex; gap: 6px; }
.days-select { background: #2a2a3e; color: #e0e0e0; border: 1px solid #3a3a4e; border-radius: 4px; padding: 2px 6px; font-size: 12px; }
.refresh-btn { background: #3b82f6; color: white; border: none; border-radius: 4px; padding: 3px 10px; cursor: pointer; font-size: 12px; }
.refresh-btn:disabled { opacity: 0.5; }
.loading, .error, .empty { text-align: center; padding: 20px; color: #a0a0b0; }
.error { color: #ef4444; }
.ensemble-card { background: #1e1e32; border-radius: 8px; padding: 12px; display: flex; gap: 12px; align-items: center; margin-bottom: 12px; }
.ensemble-icon { font-size: 28px; }
.ensemble-trend { font-size: 15px; margin-bottom: 4px; }
.ensemble-trend strong { font-size: 16px; }
.confidence { margin-left: 8px; background: #3b82f6; color: white; padding: 1px 6px; border-radius: 8px; font-size: 11px; }
.ensemble-price { font-size: 12px; color: #a0a0b0; }
.model-votes, .patterns-section, .levels-section, .accuracy-section { margin-bottom: 12px; }
.accuracy-section h4 { margin: 0 0 8px; font-size: 13px; color: #a0a0b0; }
.accuracy-item { display: flex; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid #2a2a3e; }
.accuracy-label { color: #e0e0e0; flex: 1; }
.accuracy-value { font-weight: 600; color: #a0a0b0; }
.accuracy-value.good { color: #22c55e; }
.accuracy-value.bad { color: #ef4444; }
.accuracy-samples { font-size: 11px; color: #707080; }
.accuracy-loading, .accuracy-empty { color: #707080; padding: 6px 0; }
.model-votes h4, .patterns-section h4, .levels-section h4 { margin: 0 0 8px; font-size: 13px; color: #a0a0b0; }
.vote-item { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #2a2a3e; }
.vote-label { color: #e0e0e0; }
.vote-confidence { color: #a0a0b0; }
.text-up { color: #ef4444; }
.text-down { color: #22c55e; }
.text-sideways { color: #eab308; }
.pattern-item { display: flex; justify-content: space-between; padding: 4px 0; }
.level-row { display: flex; justify-content: space-between; padding: 4px 0; }
.level-label { color: #a0a0b0; }
</style>