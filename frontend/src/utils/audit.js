export function reconcileCounts(summary = {}) {
  const previousLeft = Number(summary.previous_records || 0)
  const previousRight = Number(summary.deleted || 0) + Number(summary.modified || 0) + Number(summary.unchanged || 0) + Number(summary.ambiguous_previous || 0)
  const currentLeft = Number(summary.current_records || 0)
  const currentRight = Number(summary.added || 0) + Number(summary.modified || 0) + Number(summary.unchanged || 0) + Number(summary.ambiguous_current || 0)
  return {
    previousLeft,
    previousRight,
    currentLeft,
    currentRight,
    previousPass: previousLeft === previousRight,
    currentPass: currentLeft === currentRight,
    passed: previousLeft === previousRight && currentLeft === currentRight,
  }
}

export function formatNumber(value) {
  if (value === null || value === undefined || value === '') return 'Not available'
  return Number(value).toLocaleString()
}

export function formatPercent(value) {
  if (value === null || value === undefined || value === '') return 'Not available'
  return `${Number(value).toFixed(2)}%`
}

export function formatTimestamp(value) {
  if (!value) return 'Not available'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function recordLists(analysis) {
  const changes = analysis?.changes || {}
  return [
    ...(changes.added_records?.records || []),
    ...(changes.deleted_records?.records || []),
    ...(changes.modified_records?.records || []),
    ...(changes.ambiguous_matches || []),
  ]
}

export function findingMetric(finding) {
  const evidence = finding?.supporting_evidence || {}
  const value = evidence.area_removal_rate_pct ?? evidence.area_addition_rate_pct
  return value === undefined ? null : value
}

export function parseCsvHeaders(file) {
  return file.text().then((text) => text.replace(/^\uFEFF/, '').split(/\r?\n/)[0].split(',').map((header) => header.trim()))
}
