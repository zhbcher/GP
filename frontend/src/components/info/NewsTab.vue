<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'

const infoStore = useInfoStore()
const news = computed(() => infoStore.news)

function openUrl(url?: string) {
  if (url) window.open(url, '_blank', 'noopener')
}
</script>

<template>
  <div class="news-tab">
    <div
      v-if="infoStore.newsLoading"
      class="loading"
    >
      加载中...
    </div>
    <template v-else-if="news.length">
      <div
        v-for="(item, idx) in news"
        :key="item.id ?? idx"
        class="news-item"
        :class="{ clickable: !!item.url }"
        @click="openUrl(item.url)"
      >
        <div class="news-title">
          {{ item.title }}
        </div>
        <div class="news-meta">
          <span
            v-if="item.source"
            class="news-source"
          >{{ item.source }}</span>
          <span
            v-if="item.time"
            class="news-time"
          >{{ item.time }}</span>
        </div>
      </div>
    </template>
    <div
      v-else
      class="empty"
    >
      暂无数据
    </div>
  </div>
</template>

<style scoped>
.news-tab {
  padding: 8px 12px;
}

.loading,
.empty {
  font-size: 12px;
  color: #8b949e;
  padding: 12px 0;
}

.news-item {
  padding: 10px 4px;
  border-bottom: 1px solid #21262d;
}

.news-item.clickable {
  cursor: pointer;
}

.news-item.clickable:hover .news-title {
  color: #58a6ff;
}

.news-title {
  font-size: 13px;
  color: #e6edf3;
  line-height: 1.4;
  margin-bottom: 4px;
  transition: color 0.1s;
}

.news-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #8b949e;
}

.news-source {
  color: #58a6ff;
}
</style>
