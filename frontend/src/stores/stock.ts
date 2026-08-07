import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { KlineData } from '@/types'

export const useStockStore = defineStore('stock', () => {
  const currentCode = ref('')
  const currentName = ref('')
  const period = ref<'timeline' | 'minute' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly' | 'yearly'>('daily')
  const adjust = ref<'qfq' | 'hfq' | 'none'>('qfq')
  const klineData = ref<KlineData[]>([])
  const loading = ref(false)

  const dataCount = computed(() => klineData.value.length)

  function setStock(code: string, name: string) {
    currentCode.value = code
    currentName.value = name
  }

  function setPeriod(p: 'timeline' | 'minute' | '5min' | '15min' | '30min' | '60min' | 'daily' | 'weekly' | 'monthly' | 'yearly') {
    period.value = p
  }

  function setAdjust(a: 'qfq' | 'hfq' | 'none') {
    adjust.value = a
  }

  function setKline(data: KlineData[]) {
    klineData.value = data
  }

  return {
    currentCode, currentName, period, adjust,
    klineData, loading, dataCount,
    setStock, setPeriod, setAdjust, setKline,
  }
})
