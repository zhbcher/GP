<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'

const infoStore = useInfoStore()
const announcements = computed(() => infoStore.announcements)

function openUrl(url?: string) {
  if (url) window.open(url, '_blank', 'noopener')
}
</script>

<template>
  <div class="announcement-tab">
    <div
      v-if="infoStore.announcementsLoading"
      class="loading"
    >
      加载中...
    </div>
    <template v-else-if="announcements.length">
      <div
        v-for="(item, idx) in announcements"
        :key="item.id ?? idx"
        class="ann-item"
        :class="{ clickable: !!item.url, negative: item.is_negative }"
        @click="openUrl(item.url)"
      >
        <div class="ann-main">
          <span class="ann-title">{{ item.title }}</span>
          <span
            v-if="item.type"
            class="ann-type"
            :class="{ negative: item.is_negative }"
          >
            {{ item.type }}
          </span>
        </div>
        <div
          v-if="item.date"
          class="ann-date"
        >
          {{ item.date }}
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
.announcement-tab {
  padding: 8px 12px;
}

.loading,
.empty {
  font-size: 12px;
  color: #8b949e;
  padding: 12px 0;
}

.ann-item {
  padding: 10px 4px;
  border-bottom: 1px solid #21262d;
}

.ann-item.clickable {
  cursor: pointer;
}

.ann-item.clickable:hover .ann-title {
  color: #58a6ff;
}

.ann-main {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}

.ann-title {
  flex: 1;
  font-size: 13px;
  color: #e6edf3;
  line-height: 1.4;
  transition: color 0.1s;
}

.ann-item.negative .ann-title {
  color: #f85149;
}

.ann-type {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  background: #161b22;
  border: 1px solid #30363d;
  color: #8b949e;
}

.ann-type.negative {
  background: rgba(248, 81, 73, 0.12);
  border-color: rgba(248, 81, 73, 0.4);
  color: #f85149;
}

.ann-date {
  font-size: 11px;
  color: #8b949e;
  font-family: monospace;
}
</style>
