// 数字格式化工具：金额用"亿/万"，百分比保留2位

export function formatAmount(val?: number | null): string {
  if (val == null || Number.isNaN(val)) return '--'
  const abs = Math.abs(val)
  const sign = val < 0 ? '-' : ''
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}亿`
  if (abs >= 1e4) return `${sign}${(abs / 1e4).toFixed(2)}万`
  return `${sign}${abs.toFixed(2)}`
}

export function formatPct(val?: number | null, digits = 2): string {
  if (val == null || Number.isNaN(val)) return '--'
  return `${val.toFixed(digits)}%`
}

export function formatNumber(val?: number | null, digits = 2): string {
  if (val == null || Number.isNaN(val)) return '--'
  return val.toFixed(digits)
}

export function formatSignedPct(val?: number | null, digits = 2): string {
  if (val == null || Number.isNaN(val)) return '--'
  const sign = val > 0 ? '+' : ''
  return `${sign}${val.toFixed(digits)}%`
}

/** 涨跌样式类：红涨绿跌（A股习惯） */
export function upDownClass(val?: number | null): 'up' | 'down' | 'flat' {
  if (val == null || val === 0) return 'flat'
  return val > 0 ? 'up' : 'down'
}
