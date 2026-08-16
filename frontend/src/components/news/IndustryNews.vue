<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { newsApi } from '@/api'
import type { NewsSectorInfo, NewsDayInfo, IndustryNewsItem } from '@/types'

const emit = defineEmits<{ (e: 'back'): void }>()

const SECTOR_NAMES: Record<string, string> = {
  ai: 'AI/大模型', semi: '半导体', robot: '机器人', auto: '新能源车',
  energy: '能源', bio: '生物医药', space: '航天', security: '网络安全',
  tech: '科技互联网', consumer: '消费电子', macro: '财经宏观', science: '科学前沿',
}

const SECTOR_COLORS: Record<string, string> = {
  ai: '#a371f7', semi: '#f0883e', robot: '#58a6ff', auto: '#3fb950',
  energy: '#d29922', bio: '#f778ba', space: '#79c0ff', security: '#f85149',
  tech: '#58a6ff', consumer: '#d2a8ff', macro: '#ffa657', science: '#7ee787',
}

// State
const sectors = ref<NewsSectorInfo[]>([])
const activeSector = ref('')
const days = ref<NewsDayInfo[]>([])
const activeDate = ref('')
const digest = ref<string[]>([])
const items = ref<IndustryNewsItem[]>([])
const loading = ref(false)
const dayLoading = ref(false)
const refreshing = ref(false)
const error = ref('')
const expandedId = ref<number | null>(null)

const activeSectorName = computed(() => SECTOR_NAMES[activeSector.value] || activeSector.value)

function fmtDayLabel(dateStr: string) {
  const today = new Date()
  const todayStr = today.toLocaleDateString('sv-SE')
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = yesterday.toLocaleDateString('sv-SE')
  if (dateStr === todayStr) return '今天'
  if (dateStr === yesterdayStr) return '昨天'
  const d = new Date(dateStr + 'T00:00:00+08:00')
  const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  return `${d.getMonth() + 1}/${d.getDate()} ${weekdays[d.getDay()]}`
}

function fmtTime(dateStr: string) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return dateStr.slice(11, 16) || dateStr.slice(0, 10)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function sectorColor(sector: string) {
  return SECTOR_COLORS[sector] || '#8b949e'
}

function toggleExpand(id: number | undefined) {
  if (id == null) return
  expandedId.value = expandedId.value === id ? null : id
}

function displayTitle(item: IndustryNewsItem) {
  return item.title_zh || item.title
}

function displayContent(item: IndustryNewsItem) {
  return item.content_zh || item.content || item.summary || ''
}

// Load sectors on mount
async function loadSectors() {
  loading.value = true
  error.value = ''
  try {
    const res = await newsApi.sectors()
    sectors.value = res.sectors || []
    refreshing.value = res.refreshing || false
    if (sectors.value.length && !activeSector.value) {
      await selectSector(sectors.value[0].sector)
    }
  } catch (e: any) {
    error.value = '加载失败：' + (e.message || e)
  } finally {
    loading.value = false
  }
}

// Select a sector → load its days → auto-select first day with content
async function selectSector(sector: string) {
  if (sector === activeSector.value && days.value.length) return
  activeSector.value = sector
  expandedId.value = null
  dayLoading.value = true
  try {
    const res = await newsApi.sectorDays(sector)
    days.value = res.days || []
    // Pick first day with content
    const withContent = days.value.find(d => d.count > 0)
    if (withContent) {
      await loadDay(withContent.date)
    } else {
      activeDate.value = ''
      digest.value = []
      items.value = []
    }
  } catch (e: any) {
    error.value = '加载失败：' + (e.message || e)
  } finally {
    dayLoading.value = false
  }
}

// Load a specific day's news
async function loadDay(date: string) {
  activeDate.value = date
  dayLoading.value = true
  expandedId.value = null
  try {
    const res = await newsApi.sectorDay(activeSector.value, date)
    digest.value = res.digest || []
    items.value = res.items || []
  } catch (e: any) {
    error.value = '加载失败：' + (e.message || e)
  } finally {
    dayLoading.value = false
  }
}

async function refresh() {
  refreshing.value = true
  try {
    await newsApi.refresh()
    const poll = setInterval(async () => {
      try {
        const res = await newsApi.sectors()
        refreshing.value = res.refreshing
        if (!res.refreshing) {
          clearInterval(poll)
          sectors.value = res.sectors || []
          // Reload current sector
          days.value = []
          await selectSector(activeSector.value)
        }
      } catch {
        clearInterval(poll)
        refreshing.value = false
      }
    }, 5000)
  } catch (e: any) {
    error.value = '刷新失败：' + (e.message || e)
    refreshing.value = false
  }
}

onMounted(loadSectors)
</script>

<template>
  <div class="news-overlay">
    <div class="news-header">
      <button
        class="back-btn"
        @click="emit('back')"
      >
        ← 返回
      </button>
      <h2>行业资讯</h2>
      <div class="header-right">
        <button
          class="refresh-btn"
          :disabled="refreshing"
          @click="refresh"
        >
          {{ refreshing ? '抓取中...' : '⟳ 刷新' }}
        </button>
      </div>
    </div>

    <div class="news-body">
      <!-- Left: sector nav -->
      <div class="sector-nav">
        <button
          v-for="s in sectors"
          :key="s.sector"
          :class="['sector-btn', { active: activeSector === s.sector }]"
          @click="selectSector(s.sector)"
        >
          <span
            class="sector-dot"
            :style="{ background: sectorColor(s.sector) }"
          />
          <span class="sector-label">{{ SECTOR_NAMES[s.sector] || s.sector }}</span>
          <span class="sector-count">{{ s.count }}</span>
        </button>
      </div>

      <!-- Right: content -->
      <div class="content-area">
        <div
          v-if="loading || dayLoading"
          class="empty"
        >
          加载中...
        </div>
        <div
          v-else-if="error"
          class="empty"
        >
          {{ error }}
        </div>
        <template v-else>
          <!-- Date tabs -->
          <div class="date-tabs">
            <button
              v-for="d in days"
              :key="d.date"
              :class="['date-tab', { active: activeDate === d.date }]"
              @click="loadDay(d.date)"
            >
              <span class="tab-label">{{ fmtDayLabel(d.date) }}</span>
              <span class="tab-count">{{ d.count }}</span>
            </button>
          </div>

          <!-- Digest -->
          <div
            v-if="digest.length"
            class="digest-box"
          >
            <div class="digest-title">
              📌 {{ activeSectorName }} · {{ fmtDayLabel(activeDate) }}要点
            </div>
            <ol class="digest-list">
              <li
                v-for="(p, i) in digest"
                :key="i"
              >
                {{ p }}
              </li>
            </ol>
          </div>

          <!-- News list -->
          <div
            v-if="items.length"
            class="news-list"
          >
            <div
              v-for="item in items"
              :key="item.id || item.title"
              class="news-card"
              @click="toggleExpand(item.id)"
            >
              <div class="card-header">
                <span class="card-source">{{ item.source }}</span>
                <span class="card-time">{{ fmtTime(item.date) }}</span>
              </div>
              <div class="card-title">
                {{ displayTitle(item) }}
              </div>

              <div
                v-if="expandedId === item.id"
                class="card-content"
              >
                <p>{{ displayContent(item) }}</p>
                <a
                  v-if="item.link"
                  :href="item.link"
                  target="_blank"
                  class="origin-link"
                  @click.stop
                >🔗 原文链接</a>
              </div>
              <div
                v-else-if="item.content || item.content_zh"
                class="card-hint"
              >
                点击展开全文
              </div>
            </div>
          </div>
          <div
            v-else
            class="empty"
          >
            当日暂无资讯
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.news-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  flex-direction: column;
  background: #0d1117;
}
.news-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  border-bottom: 1px solid #30363d;
  background: #161b22;
  flex-shrink: 0;
}
.news-header h2 { margin: 0; font-size: 16px; color: #e6edf3; }
.back-btn {
  padding: 6px 12px;
  font-size: 13px;
  color: #8b949e;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  cursor: pointer;
}
.back-btn:hover { color: #e6edf3; border-color: #8b949e; }
.header-right { margin-left: auto; }
.refresh-btn {
  padding: 6px 14px;
  font-size: 13px;
  color: #fff;
  background: #238636;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
.refresh-btn:hover:not(:disabled) { background: #2ea043; }
.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.news-body { display: flex; flex: 1; overflow: hidden; }

/* Left sector nav */
.sector-nav {
  width: 170px;
  padding: 12px;
  overflow-y: auto;
  border-right: 1px solid #30363d;
  background: #161b22;
  flex-shrink: 0;
}
.sector-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 4px;
  font-size: 13px;
  color: #8b949e;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
}
.sector-btn:hover { background: #21262d; color: #e6edf3; }
.sector-btn.active { background: #1f6feb33; color: #58a6ff; }
.sector-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.sector-label { flex: 1; }
.sector-count {
  font-size: 11px;
  padding: 1px 6px;
  background: #30363d;
  border-radius: 8px;
}
.sector-btn.active .sector-count { background: #1f6feb44; }

/* Right content */
.content-area { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }

.date-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 20px;
  border-bottom: 1px solid #30363d;
  background: #161b22;
  overflow-x: auto;
  flex-shrink: 0;
}
.date-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 13px;
  color: #8b949e;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}
.date-tab:hover { background: #21262d; color: #e6edf3; }
.date-tab.active { background: #1f6feb33; color: #58a6ff; border-color: #1f6feb55; }
.tab-count {
  font-size: 11px;
  padding: 1px 6px;
  background: #30363d;
  border-radius: 8px;
}
.date-tab.active .tab-count { background: #1f6feb44; }

.digest-box {
  margin: 16px 20px 0;
  padding: 14px 18px;
  background: rgba(163, 113, 247, 0.08);
  border: 1px solid rgba(163, 113, 247, 0.3);
  border-radius: 10px;
}
.digest-title { font-size: 14px; font-weight: 600; color: #a371f7; margin-bottom: 10px; }
.digest-list { margin: 0; padding-left: 20px; }
.digest-list li { font-size: 13px; color: #e6edf3; line-height: 1.8; }

.news-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 20px;
  max-width: 900px;
}
.news-card {
  padding: 12px 16px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.news-card:hover { border-color: #58a6ff; }
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.card-source { font-size: 11px; color: #58a6ff; }
.card-time { font-size: 11px; color: #484f58; margin-left: auto; }
.card-title { font-size: 14px; color: #e6edf3; line-height: 1.6; font-weight: 500; }
.card-hint { font-size: 11px; color: #484f58; margin-top: 6px; }
.card-content { margin-top: 10px; padding-top: 10px; border-top: 1px solid #21262d; }
.card-content p {
  font-size: 13px;
  color: #c9d1d9;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0 0 10px;
}
.origin-link { font-size: 12px; color: #58a6ff; text-decoration: none; }
.origin-link:hover { text-decoration: underline; }

.empty { padding: 40px; text-align: center; font-size: 13px; color: #8b949e; }
</style>
