import { defineStore } from 'pinia'
import { ref } from 'vue'
import { infoApi } from '@/api'
import type {
  StockOverview, NewsItem, AnnouncementItem, ReportsResponse, FinanceData, ProfileData,
} from '@/types'

type TabKey = 'overview' | 'news' | 'announcements' | 'reports' | 'finance' | 'profile'

export const useInfoStore = defineStore('info', () => {
  const currentCode = ref('')

  // 各 Tab 数据
  const overview = ref<StockOverview | null>(null)
  const news = ref<NewsItem[]>([])
  const announcements = ref<AnnouncementItem[]>([])
  const reports = ref<ReportsResponse | null>(null)
  const finance = ref<FinanceData | null>(null)
  const profile = ref<ProfileData | null>(null)

  // 加载状态
  const overviewLoading = ref(false)
  const newsLoading = ref(false)
  const announcementsLoading = ref(false)
  const reportsLoading = ref(false)
  const financeLoading = ref(false)
  const profileLoading = ref(false)

  // 懒加载标记：已请求过的 Tab
  const loadedTabs = ref<Set<TabKey>>(new Set())

  function reset() {
    overview.value = null
    news.value = []
    announcements.value = []
    reports.value = null
    finance.value = null
    profile.value = null
    loadedTabs.value = new Set()
  }

  /** 切换股票时调用：刷新概览和资讯，清空其余（懒加载） */
  async function switchStock(code: string) {
    if (!code) return
    if (code === currentCode.value) return
    currentCode.value = code
    reset()
    // 概览 + 资讯自动刷新
    await Promise.all([loadOverview(code), loadNews(code)])
  }

  async function loadOverview(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    overviewLoading.value = true
    try {
      overview.value = await infoApi.overview(c)
      loadedTabs.value.add('overview')
    } catch {
      overview.value = null
    } finally {
      overviewLoading.value = false
    }
  }

  async function loadNews(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    newsLoading.value = true
    try {
      news.value = await infoApi.news(c)
      loadedTabs.value.add('news')
    } catch {
      news.value = []
    } finally {
      newsLoading.value = false
    }
  }

  async function loadAnnouncements(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    announcementsLoading.value = true
    try {
      announcements.value = await infoApi.announcements(c)
      loadedTabs.value.add('announcements')
    } catch {
      announcements.value = []
    } finally {
      announcementsLoading.value = false
    }
  }

  async function loadReports(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    reportsLoading.value = true
    try {
      reports.value = await infoApi.reports(c)
      loadedTabs.value.add('reports')
    } catch {
      reports.value = null
    } finally {
      reportsLoading.value = false
    }
  }

  async function loadFinance(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    financeLoading.value = true
    try {
      finance.value = await infoApi.finance(c)
      loadedTabs.value.add('finance')
    } catch {
      finance.value = null
    } finally {
      financeLoading.value = false
    }
  }

  async function loadProfile(code?: string) {
    const c = code || currentCode.value
    if (!c) return
    profileLoading.value = true
    try {
      profile.value = await infoApi.profile(c)
      loadedTabs.value.add('profile')
    } catch {
      profile.value = null
    } finally {
      profileLoading.value = false
    }
  }

  /** 懒加载入口：首次点击某 Tab 时请求 */
  function ensureLoaded(tab: TabKey) {
    if (loadedTabs.value.has(tab)) return
    switch (tab) {
      case 'overview': return loadOverview()
      case 'news': return loadNews()
      case 'announcements': return loadAnnouncements()
      case 'reports': return loadReports()
      case 'finance': return loadFinance()
      case 'profile': return loadProfile()
    }
  }

  return {
    currentCode,
    overview, news, announcements, reports, finance, profile,
    overviewLoading, newsLoading, announcementsLoading,
    reportsLoading, financeLoading, profileLoading,
    loadedTabs,
    switchStock, ensureLoaded,
    loadOverview, loadNews, loadAnnouncements, loadReports, loadFinance, loadProfile,
    reset,
  }
})
