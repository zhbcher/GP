<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { usePredictStore } from '@/stores/predict'
import { useStockStore } from '@/stores/stock'
import { predictApi, type ModelAccuracy, type BacktestStat } from '@/api'

// D3: 模型准确率（回测统计，与当前股票无关，面板打开时加载）
const accuracyModels = ref<ModelAccuracy[]>([])
const accuracyLoading = ref(false)
const MODEL_LABELS: Record<string, string> = {
  technical: '技术指标', statistical: '统计模型', monte_carlo: '蒙特卡洛',
  ml: 'XGBoost', xgboost: 'XGBoost', patterns: '形态识别', deep_learning: 'LSTM', ensemble: '集成',
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
const backtest = ref<Record<string, Record<string, BacktestStat>>>({})
async function loadBacktest() {
  try {
    const resp = await predictApi.backtest()
    backtest.value = resp.horizons || {}
  } catch (e) {
    backtest.value = {}
  }
}
onMounted(() => { loadAccuracy(); loadBacktest() })

const predictStore = usePredictStore()
const stockStore = useStockStore()

const days = ref(5)
const llmLoading = ref(false)

watch(() => stockStore.currentCode, () => {
  if (predictStore.visible && stockStore.currentCode) {
    predictStore.load(stockStore.currentCode, days.value)
  }
})

// 打开面板时若当前股票还没预测结果，自动加载
watch(() => predictStore.visible, (v) => {
  if (v && stockStore.currentCode && !predictStore.result) {
    predictStore.load(stockStore.currentCode, days.value)
  }
})

function refresh() {
  if (stockStore.currentCode) {
    predictStore.load(stockStore.currentCode, days.value)
  }
}

async function generateLlm() {
  if (!stockStore.currentCode) return
  llmLoading.value = true
  try {
    await predictStore.load(stockStore.currentCode, days.value, true)
  } finally {
    llmLoading.value = false
  }
}

const ensemble = computed(() => {
  const e = predictStore.result?.ensemble
  if (!e || 'error' in e) return null
  return e
})

const voteRows = computed(() => {
  const en = ensemble.value
  if (!en || !en.votes) return []
  const labels: Record<string, string> = {
    technical: '技术指标', statistical: '统计模型', monte_carlo: '蒙特卡洛',
    ml: 'XGBoost', patterns: '形态识别', deep_learning: 'LSTM',
  }
  return Object.entries(en.votes).map(([name, v]) => ({
    name,
    label: labels[name] || name,
    direction: v.direction,
    confidence: v.confidence,
    weight: v.weight,
    trendText: v.direction > 0 ? '↑ 看涨' : v.direction < 0 ? '↓ 看跌' : '→ 震荡',
    trendClass: v.direction > 0 ? 'up' : v.direction < 0 ? 'down' : 'sideways',
  }))
})

const modelVotes = computed(() => voteRows.value)

const trendEmoji = computed(() => {
  const t = ensemble.value?.final_trend
  if (t === 'up') return '📈'
  if (t === 'down') return '📉'
  return '📊'
})

const trendLabel = computed(() => {
  const t = ensemble.value?.final_trend
  if (t === 'up') return '看涨'
  if (t === 'down') return '看跌'
  return '震荡'
})

const trendClass = computed(() => {
  const t = ensemble.value?.final_trend
  return t === 'up' ? 'up' : t === 'down' ? 'down' : 'sideways'
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
    <div v-else-if="ensemble" class="predict-content">
      <!-- 综合趋势 -->
      <div class="ensemble-card">
        <div class="ensemble-icon">{{ trendEmoji }}</div>
        <div class="ensemble-info">
          <div class="ensemble-trend">
            综合趋势: <strong :class="'text-' + trendClass">{{ trendLabel }}</strong>
            <span class="confidence">{{ (ensemble.weighted_confidence * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="ensemble.target_price" class="ensemble-price">
            目标价: {{ ensemble.target_price }}
            <span v-if="ensemble.score !== undefined" class="ensemble-score">（得分 {{ ensemble.score > 0 ? '+' : '' }}{{ ensemble.score.toFixed(2) }}）</span>
          </div>
        </div>
      </div>

      <!-- 各模型投票（加权） -->
      <div class="model-votes">
        <h4>模型投票（权重来自回测准确率）</h4>
        <div v-for="item in voteRows" :key="item.name" class="vote-item">
          <span class="vote-label">{{ item.label }}</span>
          <span :class="['vote-trend', 'text-' + item.trendClass]">{{ item.trendText }}</span>
          <span class="vote-confidence">{{ (item.confidence * 100).toFixed(0) }}%</span>
          <span class="vote-weight">权重 {{ item.weight.toFixed(2) }}</span>
        </div>
      </div>

      <!-- 回测准确率（walk-forward 历史验证） -->
      <div class="accuracy-section">
        <h4>模型准确率（历史回测 / 近{{ days }}日方向）</h4>
        <div v-if="Object.keys(backtest).length === 0" class="accuracy-empty">暂无回测数据</div>
        <template v-else>
          <div v-for="(stat, model) in (backtest[String(days)] || {})" :key="model" class="accuracy-item">
            <span class="accuracy-label">{{ MODEL_LABELS[model] || model }}</span>
            <span class="accuracy-value" :class="{ good: stat.accuracy >= 0.53, bad: stat.accuracy < 0.50 }">{{ (stat.accuracy * 100).toFixed(1) }}%</span>
            <span class="accuracy-samples">{{ stat.total }} 样本</span>
          </div>
          <div class="accuracy-note">权重按回测准确率分配；&lt;50% 的模型已被压权</div>
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

      <!-- LLM 分析报告 -->
      <div class="llm-section">
        <h4>AI 分析报告</h4>
        <div v-if="llmLoading" class="loading">AI 分析生成中（约 10-30 秒）...</div>
        <template v-else-if="predictStore.result?.llm">
          <div v-if="predictStore.result.llm.status === 'ok'" class="llm-report">
            <p class="llm-summary">{{ predictStore.result.llm.summary }}</p>
            <p class="llm-suggestion">💡 {{ predictStore.result.llm.suggestion }}</p>
            <p class="llm-risk">⚠️ 风险: {{ predictStore.result.llm.risk }}</p>
          </div>
          <div v-else class="llm-error">
            {{ predictStore.result.llm.status === 'not_configured' ? '未配置 LLM API' : '生成失败: ' + (predictStore.result.llm.error || predictStore.result.llm.status) }}
          </div>
        </template>
        <button v-else class="llm-btn" @click="generateLlm">✨ 生成 AI 分析报告</button>
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
.model-votes, .patterns-section, .levels-section, .accuracy-section, .llm-section { margin-bottom: 12px; }
.ensemble-score { color: #707080; font-size: 11px; }
.llm-section h4 { margin: 0 0 8px; font-size: 13px; color: #a0a0b0; }
.llm-btn { background: #6366f1; color: white; border: none; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 12px; width: 100%; }
.llm-btn:hover { background: #818cf8; }
.llm-report { background: #1e1e32; border-radius: 8px; padding: 10px; line-height: 1.6; }
.llm-summary { margin: 0 0 8px; color: #e0e0e0; }
.llm-suggestion { margin: 0 0 6px; color: #93c5fd; }
.llm-risk { margin: 0; color: #fbbf24; font-size: 12px; }
.llm-error { color: #707080; font-size: 12px; }
.accuracy-section h4 { margin: 0 0 8px; font-size: 13px; color: #a0a0b0; }
.accuracy-item { display: flex; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid #2a2a3e; }
.accuracy-label { color: #e0e0e0; flex: 1; }
.accuracy-value { font-weight: 600; color: #a0a0b0; }
.accuracy-value.good { color: #22c55e; }
.accuracy-value.bad { color: #ef4444; }
.accuracy-samples { font-size: 11px; color: #707080; }
.accuracy-loading, .accuracy-empty { color: #707080; padding: 6px 0; }
.accuracy-note { color: #606070; font-size: 11px; margin-top: 4px; }
.model-votes h4, .patterns-section h4, .levels-section h4 { margin: 0 0 8px; font-size: 13px; color: #a0a0b0; }
.vote-item { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #2a2a3e; }
.vote-label { color: #e0e0e0; flex: 1; }
.vote-confidence { color: #a0a0b0; margin-right: 8px; }
.vote-weight { color: #707080; font-size: 11px; min-width: 56px; text-align: right; }
.text-up { color: #ef4444; }
.text-down { color: #22c55e; }
.text-sideways { color: #eab308; }
.pattern-item { display: flex; justify-content: space-between; padding: 4px 0; }
.level-row { display: flex; justify-content: space-between; padding: 4px 0; }
.level-label { color: #a0a0b0; }
</style>