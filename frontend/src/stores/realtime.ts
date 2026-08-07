import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { RealtimeQuote } from '@/types'
import { getAccessKey } from '@/api'

export const useRealtimeStore = defineStore('realtime', () => {
  const quotes = ref<Map<string, RealtimeQuote>>(new Map())
  const connected = ref(false)
  const ws = ref<WebSocket | null>(null)
  let reconnectAttempts = 0

  function connect() {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) return

    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const key = getAccessKey()
    const wsUrl = `${protocol}//${window.location.host}/ws/quote${key ? `?key=***}` : ''}`
    const socket = new WebSocket(wsUrl)
    ws.value = socket

    socket.onopen = () => {
      connected.value = true
      reconnectAttempts = 0
    }

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'quote_update') {
        for (const [code, q] of Object.entries(msg.data)) {
          quotes.value.set(code, q as RealtimeQuote)
        }
      } else if (msg.type === 'alert_triggered') {
        // BE-002: browser notification for triggered alerts
        const d = msg.data
        const text = `${d.stock_name || d.stock_code} ${d.direction === 'above' ? '涨到' : '跌到'} ${d.target_price}（当前 ${d.current_price}）`
        if (Notification.permission === 'granted') {
          new Notification('价格预警触发', { body: text })
        }
      }
    }

    socket.onclose = () => {
      connected.value = false
      // Exponential backoff reconnect: 1s, 2s, 4s, 8s, ... max 30s
      reconnectAttempts++
      const delay = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts))
      setTimeout(() => connect(), delay)
    }

    socket.onerror = () => {
      socket.close()
    }
  }

  function getQuote(code: string): RealtimeQuote | undefined {
    return quotes.value.get(code)
  }

  return {
    quotes, connected, ws,
    connect, getQuote,
  }
})