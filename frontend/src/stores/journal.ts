import { defineStore } from 'pinia'
import { ref } from 'vue'
import { journalApi } from '@/api'

export interface JournalEntry {
  id?: number
  trade_date: string
  operations: string
  market_obs: string
  plan: string
  mood: string
  created_at?: string
  updated_at?: string
}

export interface JournalSummary {
  trade_date: string
  mood: string
  summary: string
}

export interface DateAnnotation {
  id: string
  stock_code: string
  trade_date: string
  type: string
  content: string
  position: string
}

export const useJournalStore = defineStore('journal', () => {
  const entry = ref<JournalEntry>({
    trade_date: new Date().toISOString().slice(0, 10),
    operations: '',
    market_obs: '',
    plan: '',
    mood: 'neutral',
  })
  const recent = ref<JournalSummary[]>([])
  const annotations = ref<DateAnnotation[]>([])
  const loading = ref(false)
  const saving = ref(false)

  function todayStr(): string {
    return new Date().toISOString().slice(0, 10)
  }

  async function load(date: string) {
    loading.value = true
    try {
      const data = await journalApi.get(date)
      entry.value = { ...data }
      // Also load annotations for this date
      const annData = await journalApi.annotations(date)
      annotations.value = annData || []
    } finally {
      loading.value = false
    }
  }

  async function save() {
    saving.value = true
    try {
      const data = await journalApi.upsert({
        trade_date: entry.value.trade_date,
        operations: entry.value.operations,
        market_obs: entry.value.market_obs,
        plan: entry.value.plan,
        mood: entry.value.mood,
      })
      entry.value = { ...data }
      // Refresh recent list
      await loadRecent()
      return data
    } finally {
      saving.value = false
    }
  }

  async function loadRecent(days = 30) {
    const data = await journalApi.recent(days)
    recent.value = data || []
  }

  function setDate(date: string) {
    entry.value.trade_date = date
  }

  return {
    entry,
    recent,
    annotations,
    loading,
    saving,
    todayStr,
    load,
    save,
    loadRecent,
    setDate,
  }
})
