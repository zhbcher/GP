<script setup lang="ts">
import { computed } from 'vue'
import { useInfoStore } from '@/stores/info'
import { formatPct, formatSignedPct, upDownClass } from '@/utils/format'

const infoStore = useInfoStore()
const profile = computed(() => infoStore.profile)
const structure = computed(() => profile.value?.share_structure ?? [])
const holders = computed(() => profile.value?.shareholder_count ?? [])
</script>

<template>
  <div class="profile-tab">
    <div
      v-if="infoStore.profileLoading"
      class="loading"
    >
      加载中...
    </div>
    <template v-else-if="profile">
      <section
        v-if="profile.introduction"
        class="block"
      >
        <h4 class="block-title">
          公司简介
        </h4>
        <p class="text-block">
          {{ profile.introduction }}
        </p>
      </section>

      <section
        v-if="profile.main_business"
        class="block"
      >
        <h4 class="block-title">
          主营业务
        </h4>
        <p class="text-block">
          {{ profile.main_business }}
        </p>
      </section>

      <section
        v-if="structure.length"
        class="block"
      >
        <h4 class="block-title">
          股本结构
        </h4>
        <div class="struct-list">
          <div
            v-for="(s, i) in structure"
            :key="i"
            class="struct-row"
          >
            <span class="struct-name">{{ s.name || '--' }}</span>
            <div class="struct-bar-wrap">
              <div
                class="struct-bar"
                :style="{ width: formatPct(s.ratio) }"
              />
            </div>
            <span class="struct-ratio">{{ formatPct(s.ratio) }}</span>
          </div>
        </div>
      </section>

      <section
        v-if="holders.length"
        class="block"
      >
        <h4 class="block-title">
          股东户数变化
        </h4>
        <div class="holder-list">
          <div
            v-for="(h, i) in holders"
            :key="i"
            class="holder-row"
          >
            <span class="holder-date">{{ h.date || '--' }}</span>
            <span class="holder-count">{{ h.count != null ? h.count.toLocaleString() : '--' }}</span>
            <span
              class="holder-change"
              :class="upDownClass(h.change_pct)"
            >
              {{ formatSignedPct(h.change_pct) }}
            </span>
          </div>
        </div>
      </section>

      <div
        v-if="!profile.introduction && !profile.main_business && !structure.length && !holders.length"
        class="empty"
      >
        暂无数据
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
.profile-tab {
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

.text-block {
  font-size: 12px;
  color: #e6edf3;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}

.struct-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.struct-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.struct-name {
  color: #8b949e;
  min-width: 64px;
}

.struct-bar-wrap {
  flex: 1;
  height: 6px;
  background: #0d1117;
  border-radius: 3px;
  overflow: hidden;
}

.struct-bar {
  height: 100%;
  background: #58a6ff;
  border-radius: 3px;
}

.struct-ratio {
  color: #e6edf3;
  font-family: monospace;
  min-width: 48px;
  text-align: right;
}

.holder-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.holder-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 4px;
  font-size: 12px;
}

.holder-date {
  color: #8b949e;
  font-family: monospace;
}

.holder-count {
  color: #e6edf3;
  font-family: monospace;
  flex: 1;
  text-align: right;
}

.holder-change {
  font-family: monospace;
  min-width: 56px;
  text-align: right;
}

.up { color: #f85149; }
.down { color: #3fb950; }
.flat { color: #8b949e; }
</style>
