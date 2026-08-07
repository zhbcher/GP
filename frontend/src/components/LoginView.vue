<script setup lang="ts">
import { ref } from 'vue'
import { authApi, setAccessKey } from '@/api'

const accessKey = ref('')
const error = ref('')
const loading = ref(false)

const emit = defineEmits<{
  (e: 'authenticated'): void
}>()

async function doVerify() {
  if (!accessKey.value.trim()) {
    error.value = '请输入访问密钥'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await authApi.verify(accessKey.value.trim())
    setAccessKey(accessKey.value.trim())
    emit('authenticated')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '密钥错误'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-icon">📈</div>
      <h1>自选股看盘系统</h1>
      <p class="login-subtitle">请输入访问密钥</p>
      <form @submit.prevent="doVerify">
        <input
          v-model="accessKey"
          type="password"
          placeholder="访问密钥"
          autofocus
          :disabled="loading"
        />
        <p v-if="error" class="login-error">{{ error }}</p>
        <button type="submit" :disabled="loading">
          {{ loading ? '验证中...' : '进入系统' }}
        </button>
      </form>
      <p class="login-hint">提示：也可以用 URL 参数访问，如 <code>?key=***</code></p>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100vh;
  background: #0d1117;
}

.login-card {
  width: 340px;
  padding: 40px 32px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  text-align: center;
}

.login-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

h1 {
  margin: 0 0 8px;
  font-size: 20px;
  color: #e6edf3;
}

.login-subtitle {
  margin: 0 0 24px;
  font-size: 14px;
  color: #8b949e;
}

input {
  width: 100%;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 15px;
  color: #e6edf3;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.2s;
}

input:focus {
  border-color: #58a6ff;
}

.login-error {
  margin: 0 0 12px;
  font-size: 13px;
  color: #f85149;
}

button {
  width: 100%;
  padding: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: #238636;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

button:hover:not(:disabled) {
  background: #2ea043;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-hint {
  margin-top: 16px;
  font-size: 12px;
  color: #484f58;
}

.login-hint code {
  color: #8b949e;
}
</style>
