/**
 * KLineChart v10 annotation overlay + chart lifecycle management.
 * v10 changes vs v9: registerOverlay is global (not chart method),
 * circle attrs use x/y/r (not cx/cy/r), removeOverlay uses filter object.
 */
import { init, registerOverlay, registerHotkey, dispose } from 'klinecharts'
import type { Chart } from 'klinecharts'
import type { AnnotationExtendData } from '@/types/annotation'
import { ANNOTATION_COLORS } from '@/types/annotation'

let chart: Chart | null = null

export function createChart(container: HTMLElement): Chart {
  if (chart) {
    dispose(chart)
  }

  chart = init(container, {
    styles: {
      grid: {
        show: true,
        horizontal: { show: true, color: '#2e313a', size: 1 },
        vertical: { show: true, color: '#2e313a', size: 1 },
      },
      candle: {
        type: 'candle_solid',
        bar: {
          upColor: '#ef4444',
          downColor: '#22c55e',
          noChangeColor: '#9ca3af',
          upBorderColor: '#ef4444',
          downBorderColor: '#22c55e',
          upWickColor: '#ef4444',
          downWickColor: '#22c55e',
        },
        tooltip: {
          showRule: 'follow_cross',
          showType: 'standard',
          legend: {
            // v10 placeholder template; {change} auto-computes pct and auto-colors up/down
            template: [
              { title: 'time', value: '{time}' },
              { title: 'open', value: '{open}' },
              { title: 'high', value: '{high}' },
              { title: 'low', value: '{low}' },
              { title: 'close', value: '{close}' },
              { title: 'change', value: '{change}' },
              { title: 'volume', value: '{volume}' },
            ],
          },
        },
        priceMark: {
          show: true,
          high: { show: true, color: '#9ca3af', textSize: 10 },
          low: { show: true, color: '#9ca3af', textSize: 10 },
          last: { show: false },
        },
      },
      crosshair: {
        show: true,
        horizontal: { show: true, line: { style: { style: 'dashed', size: 1, color: '#4b5563' } } },
        vertical: { show: true, line: { style: { style: 'dashed', size: 1, color: '#4b5563' } } },
      },
      xAxis: { show: true, axisLine: { show: true, color: '#2e313a' }, tickLine: { show: false }, tickText: { show: true, color: '#6b7280', size: 10 } },
      yAxis: { show: true, axisLine: { show: true, color: '#2e313a' }, tickLine: { show: false }, tickText: { show: true, color: '#6b7280', size: 10 } },
      separator: { size: 1, color: '#2e313a' },
      overlay: {
        point: { color: '#fff', borderColor: '#3b82f6', borderSize: 2, radius: 4 },
        line: { smooth: false, size: 2, color: '#3b82f6' },
      },
    },
  })

  if (chart) {
    chart.setLocale('zh-CN')
    chart.setTimezone('Asia/Shanghai')
    ;(window as any).__chart = chart

    // Volume sub-chart (VOL indicator in a separate pane)
    chart.createIndicator({ name: 'VOL', paneId: 'volume_pane' }, false)

    // Default main-chart indicators: MA
    chart.createIndicator({ name: 'MA', paneId: 'candle_pane' }, true)

    // Register plain arrow-key hotkeys (v10 defaults require Shift)
    registerHotkey({
      name: 'arrowScrollLeft',
      keys: 'ArrowLeft',
      action: ({ chart }) => { chart.scrollByDistance(-3 * chart.getBarSpace().bar) },
    })
    registerHotkey({
      name: 'arrowScrollRight',
      keys: 'ArrowRight',
      action: ({ chart }) => { chart.scrollByDistance(3 * chart.getBarSpace().bar) },
    })
    registerHotkey({
      name: 'arrowZoomIn',
      keys: 'ArrowUp',
      action: ({ chart }) => { chart.zoomAtCoordinate(1.05) },
    })
    registerHotkey({
      name: 'arrowZoomOut',
      keys: 'ArrowDown',
      action: ({ chart }) => { chart.zoomAtCoordinate(0.95) },
    })
  }

  return chart!
}

export function getChart(): Chart | null {
  return chart
}

export function resizeChart() {
  chart?.resize()
}

export function destroyChart() {
  if (chart) {
    dispose(chart)
    chart = null
  }
}

/**
 * Register the annotation overlay globally (v10: global function, not chart method).
 * Must be called once before creating annotation overlays.
 */
export function registerAnnotationOverlay() {
  registerOverlay<AnnotationExtendData>({
    name: 'stockAnnotation',
    totalStep: 1,
    needDefaultPointFigure: false,
    mode: 'weak_magnet',
    modeSensitivity: 5,

    createPointFigures: (params) => {
      const { coordinates, overlay } = params
      if (coordinates.length === 0) return []
      const point = coordinates[0]
      const ext = overlay.extendData as AnnotationExtendData
      const color = ANNOTATION_COLORS[ext?.type] || '#9ca3af'
      // Offset: above → upper-left, below → lower-right
      const isAbove = ext?.position !== 'below'
      const offsetX = isAbove ? -8 : 8
      const offsetY = isAbove ? -12 : 12

      return [{
        type: 'circle',
        attrs: {
          x: point.x + offsetX,
          y: point.y + offsetY,
          r: 7,
        },
        styles: {
          style: 'fill' as const,
          color,
          borderColor: '#ffffff',
          borderSize: 2,
        },
      }]
    },

    onMouseEnter: (event) => {
      const ext = event.overlay.extendData as AnnotationExtendData
      const point = event.overlay.points[0]
      if (!point || !chart) return
      // Convert data point to pixel coordinates for tooltip positioning
      const pixel = chart.convertToPixel({ timestamp: point.timestamp!, value: point.value! })
      const p = Array.isArray(pixel) ? pixel[0] : pixel
      window.dispatchEvent(new CustomEvent('annotation-hover', {
        detail: {
          annotationId: ext.annotationId,
          type: ext.type,
          content: ext.content,
          position: ext.position,
          x: p?.x ?? 0,
          y: p?.y ?? 0,
        },
      }))
    },

    onMouseLeave: () => {
      window.dispatchEvent(new CustomEvent('annotation-hide'))
    },

    onClick: (event) => {
      const ext = event.overlay.extendData as AnnotationExtendData
      window.dispatchEvent(new CustomEvent('annotation-click', {
        detail: { annotationId: ext.annotationId },
      }))
    },
  })
}

/**
 * FE-007: Register limit-up/down marker overlay globally.
 * Draws a small triangle: red ▲ for limit-up (above high), green ▼ for limit-down (below low).
 */
export function registerLimitMarkOverlay() {
  registerOverlay<{ isUp: boolean }>({
    name: 'limitMark',
    totalStep: 1,
    needDefaultPointFigure: false,
    mode: 'weak_magnet',
    createPointFigures: (params) => {
      const { coordinates, overlay } = params
      if (coordinates.length === 0) return []
      const p = coordinates[0]
      const ext = overlay.extendData as { isUp: boolean }
      const isUp = ext?.isUp
      const size = 5
      // Triangle points
      const coords = isUp
        ? [{ x: p.x, y: p.y - size - 4 }, { x: p.x - size, y: p.y - 4 }, { x: p.x + size, y: p.y - 4 }]
        : [{ x: p.x, y: p.y + size + 4 }, { x: p.x - size, y: p.y + 4 }, { x: p.x + size, y: p.y + 4 }]
      return [{
        type: 'polygon',
        attrs: { coordinates: coords },
        styles: {
          style: 'fill' as const,
          color: isUp ? '#ef4444' : '#22c55e',
        },
      }]
    },
  })
}

export function createAnnotationOverlay(data: {
  annotationId: string
  type: string
  content: string
  position: string
  timestamp: number
  value: number
}): string | null {
  if (!chart) return null

  // Remove existing overlay with same annotationId
  const existing = chart.getOverlays({ name: 'stockAnnotation' })
  const dup = existing.find(o =>
    (o.extendData as AnnotationExtendData)?.annotationId === data.annotationId
  )
  if (dup) {
    chart.removeOverlay({ id: dup.id })
  }

  const id = chart.createOverlay({
    name: 'stockAnnotation',
    points: [{ timestamp: data.timestamp, value: data.value }],
    extendData: {
      annotationId: data.annotationId,
      type: data.type,
      content: data.content,
      position: data.position,
    } as AnnotationExtendData,
    visible: true,
  })
  return (typeof id === 'string' ? id : null)
}

export function removeAnnotationOverlay(annotationId: string) {
  if (!chart) return
  const overlays = chart.getOverlays({ name: 'stockAnnotation' })
  const overlay = overlays.find(o =>
    (o.extendData as AnnotationExtendData)?.annotationId === annotationId
  )
  if (overlay) {
    chart.removeOverlay({ id: overlay.id })
  }
}

export function clearAllOverlays() {
  if (!chart) return
  chart.removeOverlay({ name: 'stockAnnotation' })
  chart.removeOverlay({ name: 'limitMark' })
  chart.removeOverlay({ name: 'minuteAvgLine' })
}

/**
 * Register a polyline overlay for minute chart average price line.
 * Takes N points and draws connected line segments through all of them.
 */
let minuteAvgRegistered = false
export function registerMinuteAvgOverlay() {
  if (minuteAvgRegistered) return
  registerOverlay({
    name: 'minuteAvgLine',
    totalStep: 1,
    needDefaultPointFigure: false,
    lock: true,
    visible: true,
    zLevel: -1,
    createPointFigures: (params: any) => {
      const { coordinates } = params
      if (!coordinates || coordinates.length < 2) return []
      // Draw connected line segments
      const lines: any[] = []
      for (let i = 0; i < coordinates.length - 1; i++) {
        lines.push({
          type: 'line',
          attrs: {
            coordinates: [coordinates[i], coordinates[i + 1]],
          },
          styles: {
            style: 'solid' as const,
            color: '#f5c842',
            size: 1,
          },
        })
      }
      return lines
    },
  })
  minuteAvgRegistered = true
}

export function createMinuteAvgOverlay(points: { timestamp: number; value: number }[]) {
  if (!chart || points.length < 2) return
  // Remove existing
  chart.removeOverlay({ name: 'minuteAvgLine' })
  chart.createOverlay({
    name: 'minuteAvgLine',
    points: points,
    lock: true,
    visible: true,
    zLevel: -1,
  })
}

/**
 * FE-007: Limit-up/down markers.
 * Scans kline data and places triangle markers on limit-up (red ▲) / limit-down (green ▼) candles.
 */
export function markLimitCandles(klineData: { timestamp: number; open: number; high: number; low: number; close: number }[]) {
  if (!chart) return
  // Remove existing limit marks
  chart.removeOverlay({ name: 'limitMark' })

  for (let i = 1; i < klineData.length; i++) {
    const prev = klineData[i - 1]
    const cur = klineData[i]
    if (prev.close <= 0) continue
    const pct = (cur.close - prev.close) / prev.close * 100
    // Threshold: 9.8% for main board, 19.8% for ChiNext/STAR
    const threshold = 9.8
    if (Math.abs(pct) >= threshold) {
      const isUp = pct > 0
      chart.createOverlay({
        name: 'limitMark',
        points: [{ timestamp: cur.timestamp, value: isUp ? cur.high : cur.low }],
        extendData: { isUp },
        onDrawEnd: () => {},
      })
    }
  }
}