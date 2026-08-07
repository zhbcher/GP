import { defineStore } from 'pinia'
import { ref } from 'vue'
import { alertApi } from '@/api'

export const useAlertStore = defineStore('alert', () => {
  const alerts = ref<any[]>([])

  async function load(stockCode?: string) {
    alerts.value = await alertApi.list(stockCode)
  }

  async function create(data: {
    stock_code: string
    stock_name?: string
    alert_type?: string
    target_price?: number
    direction?: string
    pct_threshold?: number
    volume_ratio?: number
    volume_days?: number
  }) {
    const alert = await alertApi.create(data)
    alerts.value.unshift(alert)
    return alert
  }

  async function remove(id: number) {
    await alertApi.delete(id)
    alerts.value = alerts.value.filter(a => a.id !== id)
  }

  return { alerts, load, create, remove }
})
