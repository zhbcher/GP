import { ref } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'gp-theme'

const currentTheme = ref<ThemeMode>('dark')

function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
  currentTheme.value = theme
  syncChartTheme(theme)
}

/**
 * Sync KLineChart styles with the current theme.
 * Dark: bg #1a1a2e, text #a0a0b0, grid #2a2a3e, up #ef4444, down #22c55e
 * Light: bg #ffffff, text #333333, grid #e0e0e0, up #ef4444, down #22c55e
 */
function syncChartTheme(theme: ThemeMode) {
  // Dispatch event for KlineChartWrapper to pick up
  window.dispatchEvent(new CustomEvent('theme-change', { detail: { theme } }))
}

function getChartStyles(theme: ThemeMode) {
  if (theme === 'dark') {
    return {
      grid: {
        horizontal: { color: '#2a2a3e' },
        vertical: { color: '#2a2a3e' },
      },
      candle: {
        type: 'candle_solid',
        tooltip: {
          text: { color: '#a0a0b0' },
        },
        priceMark: {
          last: {
            upColor: '#ef4444',
            downColor: '#22c55e',
            noChangeColor: '#a0a0b0',
          },
        },
        bar: {
          upColor: '#ef4444',
          downColor: '#22c55e',
          noChangeColor: '#a0a0b0',
          upBorderColor: '#ef4444',
          downBorderColor: '#22c55e',
          noChangeBorderColor: '#a0a0b0',
          upWickColor: '#ef4444',
          downWickColor: '#22c55e',
          noChangeWickColor: '#a0a0b0',
        },
      },
      xAxis: {
        axisLine: { color: '#2a2a3e' },
        tickText: { color: '#a0a0b0' },
        tickLine: { color: '#2a2a3e' },
      },
      yAxis: {
        axisLine: { color: '#2a2a3e' },
        tickText: { color: '#a0a0b0' },
        tickLine: { color: '#2a2a3e' },
      },
      separator: {
        line: { color: '#2a2a3e' },
      },
      crosshair: {
        horizontal: {
          line: { color: '#9ca3af' },
          text: { backgroundColor: '#2a2a3e' },
        },
        vertical: {
          line: { color: '#9ca3af' },
          text: { backgroundColor: '#2a2a3e' },
        },
      },
      background: { type: 'solid', color: '#1a1a2e' },
    }
  } else {
    return {
      grid: {
        horizontal: { color: '#e0e0e0' },
        vertical: { color: '#e0e0e0' },
      },
      candle: {
        type: 'candle_solid',
        tooltip: {
          text: { color: '#333333' },
        },
        priceMark: {
          last: {
            upColor: '#ef4444',
            downColor: '#22c55e',
            noChangeColor: '#6b7280',
          },
        },
        bar: {
          upColor: '#ef4444',
          downColor: '#22c55e',
          noChangeColor: '#6b7280',
          upBorderColor: '#ef4444',
          downBorderColor: '#22c55e',
          noChangeBorderColor: '#6b7280',
          upWickColor: '#ef4444',
          downWickColor: '#22c55e',
          noChangeWickColor: '#6b7280',
        },
      },
      xAxis: {
        axisLine: { color: '#e0e0e0' },
        tickText: { color: '#333333' },
        tickLine: { color: '#e0e0e0' },
      },
      yAxis: {
        axisLine: { color: '#e0e0e0' },
        tickText: { color: '#333333' },
        tickLine: { color: '#e0e0e0' },
      },
      separator: {
        line: { color: '#e0e0e0' },
      },
      crosshair: {
        horizontal: {
          line: { color: '#9ca3af' },
          text: { backgroundColor: '#e0e0e0' },
        },
        vertical: {
          line: { color: '#9ca3af' },
          text: { backgroundColor: '#e0e0e0' },
        },
      },
      background: { type: 'solid', color: '#ffffff' },
    }
  }
}

export function useTheme() {
  // Initialize from localStorage or default to dark
  const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
  if (saved === 'light' || saved === 'dark') {
    currentTheme.value = saved
  } else {
    currentTheme.value = 'dark'
  }

  // Apply on init
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.theme = currentTheme.value
  }

  function toggle() {
    const next: ThemeMode = currentTheme.value === 'dark' ? 'light' : 'dark'
    applyTheme(next)
  }

  function setTheme(theme: ThemeMode) {
    applyTheme(theme)
  }

  function init() {
    applyTheme(currentTheme.value)
  }

  return {
    theme: currentTheme,
    toggle,
    setTheme,
    init,
    getChartStyles,
  }
}

export { getChartStyles }
