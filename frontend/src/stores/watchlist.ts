import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { watchlistApi } from '@/api'

export interface StockItem {
  id: number
  stock_code: string
  stock_name: string
  group_id: number | null
  note: string
  sort_order: number
  created_at: string
  realtime: any | null
}

export interface GroupWithStocks {
  id: number
  name: string
  sort_order: number
  stocks: StockItem[]
}

export const useWatchlistStore = defineStore('watchlist', () => {
  const groups = ref<GroupWithStocks[]>([])
  const ungrouped = ref<StockItem[]>([])
  const loading = ref(false)

  const allStocks = computed(() => {
    const stocks: StockItem[] = []
    for (const g of groups.value) {
      stocks.push(...g.stocks)
    }
    stocks.push(...ungrouped.value)
    return stocks
  })

  async function load() {
    loading.value = true
    try {
      const data = await watchlistApi.list()
      groups.value = data.groups || []
      ungrouped.value = data.ungrouped || []
    } finally {
      loading.value = false
    }
  }

  async function addStock(data: { stock_code: string; stock_name: string; note?: string; group_id?: number }) {
    await watchlistApi.create(data)
    await load()
  }

  async function removeStock(id: number) {
    await watchlistApi.delete(id)
    await load()
  }

  async function updateStock(id: number, data: any) {
    await watchlistApi.update(id, data)
    await load()
  }

  async function addGroup(name: string) {
    await watchlistApi.createGroup(name)
    await load()
  }

  async function removeGroup(id: number) {
    await watchlistApi.deleteGroup(id)
    await load()
  }

  return {
    groups, ungrouped, loading, allStocks,
    load, addStock, removeStock, updateStock, addGroup, removeGroup,
  }
})