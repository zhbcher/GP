import { defineStore } from 'pinia'
import { ref } from 'vue'
import { positionApi } from '@/api'

export interface PositionSummary {
  market_value: number
  total_cost: number
  total_profit: number
  profit_pct: number
  position_count: number
  stock_count: number
}

export const usePositionStore = defineStore('position', () => {
  const positions = ref<any[]>([])
  const summary = ref<PositionSummary | null>(null)

  async function load(stockCode?: string) {
    positions.value = await positionApi.list(stockCode)
  }

  async function loadSummary() {
    summary.value = await positionApi.summary()
  }

  async function create(data: { stock_code: string; stock_name?: string; cost_price: number; quantity: number; buy_date?: string; note?: string }) {
    const pos = await positionApi.create(data)
    positions.value.unshift(pos)
    return pos
  }

  async function update(id: number, data: any) {
    const updated = await positionApi.update(id, data)
    const idx = positions.value.findIndex(p => p.id === id)
    if (idx >= 0) positions.value[idx] = updated
    return updated
  }

  async function remove(id: number) {
    await positionApi.delete(id)
    positions.value = positions.value.filter(p => p.id !== id)
  }

  return { positions, summary, load, loadSummary, create, update, remove }
})
