<script setup lang="ts">
import { ref } from 'vue'
import { watchlistApi } from '@/api'

const show = ref(false)
const name = ref('')
const error = ref('')

async function handleCreate() {
  if (!name.value.trim()) return
  error.value = ''
  try {
    await watchlistApi.createGroup(name.value.trim())
    name.value = ''
    show.value = false
  } catch (e: any) {
    error.value = e.response?.data?.detail || '创建失败'
  }
}

function close() {
  show.value = false
  name.value = ''
  error.value = ''
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="modal-backdrop" @click.self="close">
        <div class="modal-panel">
          <h3>新建分组</h3>
          <div class="field">
            <input
              v-model="name"
              placeholder="分组名称（如：重仓、观察）"
              @keyup.enter="handleCreate"
            />
          </div>
          <div v-if="error" class="error">{{ error }}</div>
          <div class="actions">
            <button class="btn-cancel" @click="close">取消</button>
            <button class="btn-save" @click="handleCreate">创建</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-panel {
  background: #1e2028;
  border: 1px solid #2e313a;
  border-radius: 12px;
  padding: 24px;
  width: 360px;
}

.modal-panel h3 {
  font-size: 16px;
  color: #e4e4e7;
  margin-bottom: 16px;
}

.field input {
  width: 100%;
  padding: 8px 12px;
  background: #0f1117;
  border: 1px solid #2e313a;
  border-radius: 6px;
  color: #e4e4e7;
  font-size: 14px;
  outline: none;
}

.field input:focus {
  border-color: #3b82f6;
}

.error {
  color: #ef4444;
  font-size: 13px;
  margin-top: 8px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}

.btn-cancel {
  padding: 8px 16px;
  border-radius: 6px;
  background: transparent;
  color: #9ca3af;
  border: 1px solid #2e313a;
  cursor: pointer;
}

.btn-save {
  padding: 8px 16px;
  border-radius: 6px;
  background: #3b82f6;
  color: white;
  border: none;
  cursor: pointer;
}
</style>
