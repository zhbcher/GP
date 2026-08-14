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
  // 超跌反弹信号：原版 base（红点）/ 震荡增强版 consolidation（红三角）
  const signals = ref<{ date?: string, base: any[], consolidation: any[] }>({ base: [], consolidation: [] })

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

  function setSignals(sig: { date?: string, base: any[], consolidation: any[] }) {
    signals.value = sig
  }

  return {
    currentCode, currentName, period, adjust,
    klineData, loading, dataCount, signals,
    setStock, setPeriod, setAdjust, setKline, setSignals,
  }
})
