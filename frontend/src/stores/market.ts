import { defineStore } from 'pinia'
import { ref } from 'vue'
import { marketApi } from '@/api'
import type {
  LimitUpItem, NorthFlowData, DragonTigerItem, SectorItem, HotRankItem,
} from '@/types'

export const useMarketStore = defineStore('market', () => {
  const limitUp = ref<LimitUpItem[]>([])
  const northFlow = ref<NorthFlowData | null>(null)
  const dragonTiger = ref<DragonTigerItem[]>([])
  const sectors = ref<SectorItem[]>([])
  const hotRank = ref<HotRankItem[]>([])

  const loading = ref(false)
  const updatedAt = ref<string>('')

  async function loadAll() {
    loading.value = true
    try {
      const [lu, nf, dt, se, hr] = await Promise.all([
        marketApi.limitUp().catch(() => [] as LimitUpItem[]),
        marketApi.northFlow().catch(() => null as NorthFlowData | null),
        marketApi.dragonTiger().catch(() => [] as DragonTigerItem[]),
        marketApi.sectors().catch(() => [] as SectorItem[]),
        marketApi.hotRank().catch(() => [] as HotRankItem[]),
      ])
      limitUp.value = lu || []
      northFlow.value = nf
      dragonTiger.value = dt || []
      sectors.value = se || []
      hotRank.value = hr || []
      updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    } finally {
      loading.value = false
    }
  }

  return {
    limitUp, northFlow, dragonTiger, sectors, hotRank,
    loading, updatedAt,
    loadAll,
  }
})
