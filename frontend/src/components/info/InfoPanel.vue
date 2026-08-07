<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useInfoStore } from '@/stores/info'
import OverviewTab from './OverviewTab.vue'
import NewsTab from './NewsTab.vue'
import AnnouncementTab from './AnnouncementTab.vue'
import ReportTab from './ReportTab.vue'
import FinanceTab from './FinanceTab.vue'
import ProfileTab from './ProfileTab.vue'

const props = defineProps<{ stockCode: string }>()

const infoStore = useInfoStore()

type TabKey = 'overview' | 'news' | 'announcements' | 'reports' | 'finance' | 'profile'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '概览' },
  { key: 'news', label: '资讯' },
  { key: 'announcements', label: '公告' },
  { key: 'reports', label: '研报' },
  { key: 'finance', label: '财务' },
  { key: 'profile', label: '资料' },
]

const activeTab = ref<TabKey>('overview')

const currentLoading = computed(() => {
  switch (activeTab.value) {
    case 'overview': return infoStore.overviewLoading
    case 'news': return infoStore.newsLoading
    case 'announcements': return infoStore.announcementsLoading
    case 'reports': return infoStore.reportsLoading
    case 'finance': return infoStore.financeLoading
    case 'profile': return infoStore.profileLoading
    default: return false
  }
})

function selectTab(key: TabKey) {
  activeTab.value = key
  // 懒加载：首次点击才请求
  infoStore.ensureLoaded(key)
}

// 切换股票：概览和资讯自动刷新，重置到概览 Tab
watch(
  () => props.stockCode,
  (code) => {
    if (code) {
      activeTab.value = 'overview'
      infoStore.switchStock(code)
    }
  },
  { immediate: false },
)

onMounted(() => {
  if (props.stockCode) {
    infoStore.switchStock(props.stockCode)
  }
})
</script>

<template>
  <div class="info-panel">
    <div class="tab-bar">
      <button
        v-for="t in tabs"
        :key="t.key"
        :class="['tab-btn', { active: activeTab === t.key }]"
        @click="selectTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="tab-content">
      <!-- 骨架屏 -->
      <template v-if="currentLoading">
        <div class="skeleton">
          <div class="sk-line w60"></div>
          <div class="sk-grid">
            <div class="sk-cell"></div>
            <div class="sk-cell"></div>
            <div class="sk-cell"></div>
            <div class="sk-cell"></div>
          </div>
          <div class="sk-line w100"></div>
          <div class="sk-line w80"></div>
          <div class="sk-line w90"></div>
        </div>
      </template>

      <template v-else>
        <OverviewTab v-if="activeTab === 'overview'" />
        <NewsTab v-else-if="activeTab === 'news'" />
        <AnnouncementTab v-else-if="activeTab === 'announcements'" />
        <ReportTab v-else-if="activeTab === 'reports'" />
        <FinanceTab v-else-if="activeTab === 'finance'" />
        <ProfileTab v-else-if="activeTab === 'profile'" />
      </template>
    </div>
  </div>
</template>

<style scoped>
.info-panel {
  width: 320px;
  height: 100%;
  background: #161b22;
  border-left: 1px solid #30363d;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.tab-bar {
  display: flex;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
  padding: 0 4px;
}

.tab-btn {
  flex: 1;
  padding: 10px 0;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: #8b949e;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: #e6edf3;
}

.tab-btn.active {
  color: #58a6ff;
  border-bottom-color: #58a6ff;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
}

/* 骨架屏 */
.skeleton {
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sk-line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, #21262d 25%, #30363d 37%, #21262d 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.sk-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.sk-cell {
  height: 44px;
  border-radius: 6px;
  background: linear-gradient(90deg, #21262d 25%, #30363d 37%, #21262d 63%);
  background-size: 400% 100%;
  animation: shimmer 1.4s ease infinite;
}

.w60 { width: 60%; }
.w80 { width: 80%; }
.w90 { width: 90%; }
.w100 { width: 100%; }

@keyframes shimmer {
  0% { background-position: 100% 50%; }
  100% { background-position: 0 50%; }
}
</style>
