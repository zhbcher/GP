/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'klinecharts' {
  export function init(container: string | HTMLElement, styles?: Record<string, unknown>): Chart
  export function createOverlay(value: string | OverlayCreate | Array<string | OverlayCreate>): Nullable<string> | Array<Nullable<string>>
  export function registerOverlay<E = unknown>(template: OverlayTemplate<E>): void
  export function removeOverlay(filter?: OverlayFilter): boolean
  export function overrideOverlay(override: Partial<OverlayCreate>): boolean
  export function getOverlays(filter?: OverlayFilter): Overlay[]
  export function setStyles(value: string | DeepPartial<Styles>): void
  export function setLocale(locale: string): void
  export function setTimezone(timezone: string): void
  export function setSymbol(symbol: PickPartial<SymbolInfo, 'pricePrecision' | 'volumePrecision'>): void
  export function setPeriod(period: Period): void
  export function setDataLoader(loader: DataLoader): void
  export function applyNewData(data: KLineData[], more?: DataLoadMore): void
  export function updateData(data: KLineData[]): void
  export function subscribeAction(type: ActionType, callback: ActionCallback): void
  export function unsubscribeAction(type: ActionType, callback?: ActionCallback): void
  export function scrollToTimestamp(timestamp: number, animationDuration?: number): void
  export function scrollToDataIndex(dataIndex: number, animationDuration?: number): void
  export function resize(): void
  export function convertToPixel(points: Partial<Point> | Array<Partial<Point>>, filter?: ConvertFilter): Partial<Coordinate> | Array<Partial<Coordinate>>
  export function getVisibleRange(): VisibleRange
  export function getDataList(): KLineData[]

  export interface Chart {
    createOverlay: typeof createOverlay
    registerOverlay: typeof registerOverlay
    removeOverlay: typeof removeOverlay
    overrideOverlay: typeof overrideOverlay
    getOverlays: typeof getOverlays
    setStyles: typeof setStyles
    applyNewData: typeof applyNewData
    updateData: typeof updateData
    subscribeAction: typeof subscribeAction
    unsubscribeAction: typeof unsubscribeAction
    scrollToTimestamp: typeof scrollToTimestamp
    scrollToDataIndex: typeof scrollToDataIndex
    resize: typeof resize
    convertToPixel: typeof convertToPixel
    getVisibleRange: typeof getVisibleRange
    getDataList: typeof getDataList
    setSymbol: typeof setSymbol
    setPeriod: typeof setPeriod
    setDataLoader: typeof setDataLoader
    setLocale: typeof setLocale
    setTimezone: typeof setTimezone
  }

  // Overlay types
  export interface Point {
    x?: number
    y?: number
    timestamp?: number
    value?: number
  }

  export interface OverlayPointFigure {
    type: string
    attrs: Record<string, unknown>
    styles: Record<string, unknown>
  }

  export interface OverlayTemplate<E = unknown> {
    name: string
    totalStep: number
    needDefaultPointFigure?: boolean
    mode?: string
    modeSensitivity?: number
    lock?: boolean
    onMarkReady?: () => void
    createPointFigures?: (params: { coordinates: Point[] }) => OverlayPointFigure[] | undefined
    onMouseEnter?: (event: { overlay: Overlay & { extendData: E } }) => void
    onMouseLeave?: (event: { overlay: Overlay & { extendData: E } }) => void
    onClick?: (event: { overlay: Overlay & { extendData: E } }) => void
    onDrawEnd?: (event: { overlay: Overlay & { extendData: E } }) => void
  }

  export interface Overlay {
    id: string
    name: string
    points: Point[]
    extendData?: E
    visible?: boolean
    styles?: Record<string, unknown>
  }

  export interface OverlayCreate {
    name: string
    points: any[]
    extendData?: unknown
    styles?: Record<string, unknown>
    visible?: boolean
  }

  export interface OverlayFilter {
    id?: string | number
    name?: string
  }
}
