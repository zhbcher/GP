<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useJournalStore } from '@/stores/journal'

const store = useJournalStore()

const selectedDate = ref(store.todayStr())
const moodOptions = [
  { value: 'optimistic', label: '😊 乐观' },
  { value: 'neutral', label: '😐 中性' },
  { value: 'pessimistic', label: '😟 悲观' },
]

const showRecent = ref(true)

async function onSelectDate() {
  store.setDate(selectedDate.value)
  await store.load(selectedDate.value)
}

async function onSave() {
  store.setDate(selectedDate.value)
  await store.save()
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    onSave()
  }
}

onMounted(() => {
  selectedDate.value = store.todayStr()
  store.load(selectedDate.value)
  store.loadRecent()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})

// Watch for date changes from store
watch(() => store.entry.trade_date, (v) => {
  if (v && v !== selectedDate.value) selectedDate.value = v
})

function selectRecent(date: string) {
  selectedDate.value = date
  onSelectDate()
}

const annTypeLabels: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  watch: '关注',
  review: '复盘',
  other: '其他',
}
</script>

<template>
  <div class="journal-panel" @keydown="onKeydown">
    <!-- Top: date + mood -->
    <div class="jp-header">
      <input
        type="date"
        v-model="selectedDate"
        @change="onSelectDate"
        class="jp-date-input"
      />
      <div class="jp-mood-group">
        <button
          v-for="opt in moodOptions"
          :key="opt.value"
          :class="['jp-mood-btn', { active: store.entry.mood === opt.value }]"
          @click="store.entry.mood = opt.value"
        >
          {{ opt.label }}
        </button>
      </div>
    </div>

    <div class="jp-body">
      <!-- Main editor area -->
      <div class="jp-editor-area">
        <div class="jp-field">
          <label class="jp-label">今日操作</label>
          <textarea
            v-model="store.entry.operations"
            class="jp-textarea"
            rows="4"
            placeholder="记录今日买卖操作..."
          ></textarea>
        </div>
        <div class="jp-field">
          <label class="jp-label">市场观察</label>
          <textarea
            v-model="store.entry.market_obs"
            class="jp-textarea"
            rows="4"
            placeholder="大盘走势、板块轮动、资金流向..."
          ></textarea>
        </div>
        <div class="jp-field">
          <label class="jp-label">明日计划</label>
          <textarea
            v-model="store.entry.plan"
            class="jp-textarea"
            rows="4"
            placeholder="明日交易计划..."
          ></textarea>
        </div>

        <div class="jp-actions">
          <button
            class="jp-save-btn"
            @click="onSave"
            :disabled="store.saving"
          >
            {{ store.saving ? '保存中...' : '保存 (Ctrl+S)' }}
          </button>
        </div>

        <!-- Annotations summary -->
        <div class="jp-annotations">
          <div class="jp-section-title">当日标注 ({{ store.annotations.length }})</div>
          <div v-if="store.annotations.length === 0" class="jp-empty">无标注</div>
          <div v-else class="jp-ann-list">
            <div v-for="a in store.annotations" :key="a.id" class="jp-ann-item">
              <span class="jp-ann-code">{{ a.stock_code }}</span>
              <span :class="['jp-ann-type', `ann-${a.type}`]">{{ annTypeLabels[a.type] || a.type }}</span>
              <span class="jp-ann-content">{{ a.content }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Sidebar: recent journals -->
      <div class="jp-sidebar" v-if="showRecent">
        <div class="jp-section-title">最近日志</div>
        <div class="jp-recent-list">
          <div
            v-for="r in store.recent"
            :key="r.trade_date"
            :class="['jp-recent-item', { active: r.trade_date === selectedDate }]"
            @click="selectRecent(r.trade_date)"
          >
            <span class="jp-recent-date">{{ r.trade_date }}</span>
            <span class="jp-recent-mood">{{ r.mood === 'optimistic' ? '😊' : r.mood === 'pessimistic' ? '😟' : '😐' }}</span>
            <div class="jp-recent-summary">{{ r.summary }}</div>
          </div>
          <div v-if="store.recent.length === 0" class="jp-empty">暂无日志</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.journal-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0d1117;
  color: #e6edf3;
  font-size: 13px;
  overflow: hidden;
}

.jp-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #2e313a;
  flex-shrink: 0;
}

.jp-date-input {
  background: #161b22;
  border: 1px solid #30363d;
  color: #e6edf3;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
}

.jp-mood-group {
  display: flex;
  gap: 4px;
}

.jp-mood-btn {
  background: transparent;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 4px 8px;
  color: #8b949e;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}

.jp-mood-btn:hover {
  border-color: #58a6ff;
  color: #e6edf3;
}

.jp-mood-btn.active {
  background: #1f6feb33;
  border-color: #58a6ff;
  color: #58a6ff;
}

.jp-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.jp-editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  overflow-y: auto;
}

.jp-sidebar {
  width: 200px;
  border-left: 1px solid #2e313a;
  padding: 10px 8px;
  overflow-y: auto;
  flex-shrink: 0;
}

.jp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.jp-label {
  font-size: 12px;
  color: #8b949e;
  font-weight: 500;
}

.jp-textarea {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 8px;
  color: #e6edf3;
  font-size: 13px;
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

.jp-textarea:focus {
  outline: none;
  border-color: #58a6ff;
}

.jp-actions {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}

.jp-save-btn {
  background: #238636;
  border: 1px solid #2ea043;
  border-radius: 6px;
  padding: 6px 16px;
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.jp-save-btn:hover:not(:disabled) {
  background: #2ea043;
}

.jp-save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.jp-section-title {
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid #2e313a;
}

.jp-annotations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #2e313a;
}

.jp-empty {
  color: #6e7681;
  font-size: 12px;
  padding: 8px 0;
}

.jp-ann-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.jp-ann-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  background: #161b22;
  border-radius: 4px;
  font-size: 12px;
}

.jp-ann-code {
  color: #58a6ff;
  font-weight: 500;
  min-width: 60px;
}

.jp-ann-type {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.ann-buy { background: #22c55e33; color: #22c55e; }
.ann-sell { background: #ef444433; color: #ef4444; }
.ann-watch { background: #eab30833; color: #eab308; }
.ann-review { background: #3b82f633; color: #3b82f6; }
.ann-other { background: #9ca3af33; color: #9ca3af; }

.jp-ann-content {
  color: #c9d1d9;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.jp-recent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.jp-recent-item {
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}

.jp-recent-item:hover {
  background: #161b22;
  border-color: #30363d;
}

.jp-recent-item.active {
  background: #1f6feb33;
  border-color: #58a6ff;
}

.jp-recent-date {
  font-size: 12px;
  font-weight: 500;
  color: #e6edf3;
}

.jp-recent-mood {
  float: right;
  font-size: 12px;
}

.jp-recent-summary {
  font-size: 11px;
  color: #8b949e;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
