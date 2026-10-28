export const ASSISTANT_ACTIONS = Object.freeze({
  NAVIGATE_TO: 'navigate_to',
  SELECT_AREA: 'select_area',
  COMPARE_AREA: 'compare_area',
  SELECT_FINDING: 'select_finding',
  SHOW_FINDINGS: 'show_findings',
  INSPECT_RECORD: 'inspect_record',
  OPEN_EVIDENCE: 'open_evidence',
  EXPLAIN_CALCULATION: 'explain_calculation',
  RECHECK_FINDING: 'recheck_finding',
  RUN_COUNTERFACTUAL: 'run_counterfactual',
  EXPORT_REPORT: 'export_report',
  EXPORT_DRAFT: 'export_draft',
  PROPOSE_RECORD_EDIT: 'propose_record_edit',
  UNDO_RECORD_EDIT: 'undo_record_edit',
  SHOW_CHANGE_HISTORY: 'show_change_history',
  CLEAR_CHAT: 'clear_chat',
})

const REPORT_TYPES = ['summary', 'added', 'deleted', 'modified', 'findings', 'area_comparison']
const EDITABLE_FIELDS = ['name', 'age', 'gender', 'area_id', 'area_name', 'area_type', 'population_group', 'administrative_category', 'polling_station_id', 'registration_date']

export function parseAssistantCommand(message, selectedFindingId = null) {
  const text = message.trim()
  const lower = text.toLowerCase()
  const recordMatch = text.match(/\b([A-Z]{2,5}[-_]\d{1,})\b/i)
  const areaMatch = text.match(/\b([A-Z]\d{2,})\b/i)

  if (/undo|wapas|restore/i.test(text)) return { type: ASSISTANT_ACTIONS.UNDO_RECORD_EDIT }
  if (/history|change history|revision history|badlav ka history/i.test(text)) return { type: ASSISTANT_ACTIONS.SHOW_CHANGE_HISTORY }
  if (/clear chat|reset conversation|chat saaf/i.test(text)) return { type: ASSISTANT_ACTIONS.CLEAR_CHAT }
  if (/new comparison|fresh analysis|naya comparison|nayi analysis|upload.*files/i.test(text)) return { type: ASSISTANT_ACTIONS.NAVIGATE_TO, payload: { page: 'ingestion' } }
  if (/download|export|report|report.*nikal/i.test(text)) {
    if (/draft|revised| संशोधित/i.test(text)) return { type: ASSISTANT_ACTIONS.EXPORT_DRAFT }
    const reportType = lower.includes('finding') ? 'findings' : lower.includes('delete') ? 'deleted' : lower.includes('add') ? 'added' : lower.includes('modify') ? 'modified' : lower.includes('area') ? 'area_comparison' : 'summary'
    return { type: ASSISTANT_ACTIONS.EXPORT_REPORT, payload: { reportType } }
  }
  if (/recheck|dobara check|phir se check|re-?check/i.test(text)) return { type: ASSISTANT_ACTIONS.RECHECK_FINDING, payload: { findingId: selectedFindingId } }
  if (/highest|serious|important|sabse.*(serious|important)/i.test(text)) return { type: ASSISTANT_ACTIONS.SELECT_FINDING, payload: { highestPriority: true } }
  if (/show findings|findings dikhao|flags dikhao|issues dikhao/i.test(text)) return { type: ASSISTANT_ACTIONS.SHOW_FINDINGS }
  if (/evidence|passport|saboot|प्रमाण/i.test(text)) return { type: ASSISTANT_ACTIONS.OPEN_EVIDENCE, payload: { findingId: selectedFindingId } }
  if (/calculation|calculation.*samjhao|percentage.*mean|baseline.*calculate/i.test(text)) return { type: ASSISTANT_ACTIONS.EXPLAIN_CALCULATION, payload: { findingId: selectedFindingId } }
  if (/threshold|counterfactual|what if|agar.*%/i.test(text) && /\d/.test(text)) {
    const threshold = text.match(/(\d+(?:\.\d+)?)\s*%?/)?.[1]
    return { type: ASSISTANT_ACTIONS.RUN_COUNTERFACTUAL, payload: { threshold: Number(threshold), areaId: areaMatch?.[1]?.toUpperCase() } }
  }
  if (recordMatch && /inspect|check|change|badla|age|naam|name|area|record/i.test(text)) {
    const ageMatch = text.match(/(?:age|उम्र)\s*(?:to|ko|is|=)?\s*(\d{1,3})/i)
    const textEditMatch = text.match(/(?:name|नाम|area(?: name)?|gender)\s*(?:to|ko|is|=|करना है|कर do|कर दो)\s*["']?([^"']+)["']?/i)
    const editMatch = ageMatch || textEditMatch
    if (editMatch && /change|edit|kar|कर|to|ko|is|=/i.test(text)) {
      const field = ageMatch ? 'age' : /gender/i.test(text) ? 'gender' : /area name|area/i.test(text) ? 'area_name' : 'name'
      return { type: ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT, payload: { recordId: recordMatch[1], field, value: editMatch[1].trim() } }
    }
    return { type: ASSISTANT_ACTIONS.INSPECT_RECORD, payload: { recordId: recordMatch[1] } }
  }
  if (areaMatch && /compare|comparison|compare.*areas|doosre areas/i.test(text)) return { type: ASSISTANT_ACTIONS.COMPARE_AREA, payload: { areaId: areaMatch[1].toUpperCase() } }
  if (areaMatch && /area|क्षेत्र|mein|में/i.test(text)) return { type: ASSISTANT_ACTIONS.SELECT_AREA, payload: { areaId: areaMatch[1].toUpperCase() } }
  return null
}

export function validateAssistantAction(action, context) {
  if (!action || !Object.values(ASSISTANT_ACTIONS).includes(action.type)) return { valid: false, message: 'This assistant action is not supported.' }
  if (['inspect_record', 'select_area', 'compare_area', 'select_finding', 'export_report', 'export_draft', 'recheck_finding', 'propose_record_edit', 'run_counterfactual'].includes(action.type) && !context.analysis) {
    return { valid: false, message: 'Run an analysis before using this action.' }
  }
  if (action.type === ASSISTANT_ACTIONS.EXPORT_REPORT && !REPORT_TYPES.includes(action.payload?.reportType)) return { valid: false, message: 'That report type is not supported.' }
  if (action.type === ASSISTANT_ACTIONS.EXPORT_DRAFT && !context.hasConfirmedDraft) return { valid: false, message: 'Confirm a draft change before downloading the revised synthetic CSV.' }
  if (action.type === ASSISTANT_ACTIONS.OPEN_EVIDENCE && !action.payload?.findingId) return { valid: false, message: 'Select a finding before opening its evidence.' }
  if (action.type === ASSISTANT_ACTIONS.RUN_COUNTERFACTUAL && (!Number.isFinite(action.payload?.threshold) || action.payload.threshold <= 0)) return { valid: false, message: 'Give a positive threshold percentage for the what-if comparison.' }
  if (action.type === ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT) {
    if (!action.payload?.recordId || !EDITABLE_FIELDS.includes(action.payload.field)) return { valid: false, message: 'This field cannot be edited through the draft workflow.' }
    if (action.payload.field === 'age' && (!Number.isInteger(Number(action.payload.value)) || Number(action.payload.value) < 0 || Number(action.payload.value) > 120)) return { valid: false, message: 'Age must be a whole number from 0 to 120.' }
  }
  return { valid: true }
}

export function priorityRank(priority) {
  return ({ HIGH: 0, MEDIUM: 1, LOW: 2 }[priority] ?? 3)
}

export function highestFinding(findings = []) {
  return [...findings].sort((a, b) => priorityRank(a.review_priority) - priorityRank(b.review_priority) || String(a.finding_id).localeCompare(String(b.finding_id)))[0] || null
}

export function parseCsv(text) {
  const rows = []
  let row = [], cell = '', quoted = false
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i]
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i += 1 } else quoted = !quoted
    } else if (char === ',' && !quoted) { row.push(cell); cell = '' } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && text[i + 1] === '\n') i += 1
      row.push(cell); if (row.some((value) => value !== '')) rows.push(row); row = []; cell = ''
    } else cell += char
  }
  if (cell || row.length) { row.push(cell); if (row.some((value) => value !== '')) rows.push(row) }
  const [headers = [], ...data] = rows
  return data.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ''])))
}

export function serializeCsv(rows) {
  if (!rows.length) return ''
  const headers = [...new Set(rows.flatMap((row) => Object.keys(row)))]
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
  return `${headers.map(escape).join(',')}\n${rows.map((row) => headers.map((header) => escape(row[header])).join(',')).join('\n')}\n`
}

export function resolveDraftRecord(rows, recordId) {
  const matches = rows.filter((row) => row.record_id === recordId)
  if (matches.length === 0) throw new Error(`Record ${recordId} was not found in the current draft.`)
  if (matches.length > 1) throw new Error('This record ID is duplicated, so the exact row must be selected before editing.')
  return matches[0]
}

export function applyDraftChange(rows, edit) {
  const nextRows = rows.map((row) => ({ ...row }))
  const row = resolveDraftRecord(nextRows, edit.recordId)
  const previousValue = row[edit.field] ?? ''
  row[edit.field] = edit.field === 'age' ? String(Number(edit.value)) : edit.value
  return { rows: nextRows, previousValue, nextValue: row[edit.field] }
}

export { EDITABLE_FIELDS, REPORT_TYPES }
