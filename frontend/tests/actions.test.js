import assert from 'node:assert/strict'
import test from 'node:test'
import {
  ASSISTANT_ACTIONS,
  highestFinding,
  parseAssistantCommand,
  parseCsv,
  serializeCsv,
  applyDraftChange,
  resolveDraftRecord,
  validateAssistantAction,
} from '../src/assistant/actions.js'

const analysis = { analysis_id: 'ANALYSIS-1' }

test('parses supported navigation and finding commands', () => {
  assert.deepEqual(parseAssistantCommand('Show findings'), { type: ASSISTANT_ACTIONS.SHOW_FINDINGS })
  assert.deepEqual(parseAssistantCommand('Sabse serious issue kaunsa hai?'), {
    type: ASSISTANT_ACTIONS.SELECT_FINDING,
    payload: { highestPriority: true },
  })
  assert.deepEqual(parseAssistantCommand('Open evidence', 'FND-1'), {
    type: ASSISTANT_ACTIONS.OPEN_EVIDENCE,
    payload: { findingId: 'FND-1' },
  })
  assert.deepEqual(parseAssistantCommand('Naya comparison karna hai'), {
    type: ASSISTANT_ACTIONS.NAVIGATE_TO,
    payload: { page: 'ingestion' },
  })
})

test('parses record inspection and multilingual draft-edit commands', () => {
  assert.deepEqual(parseAssistantCommand('What changed in record SYN-002?'), {
    type: ASSISTANT_ACTIONS.INSPECT_RECORD,
    payload: { recordId: 'SYN-002' },
  })
  assert.deepEqual(parseAssistantCommand('Record SYN-002 ki age 44 karni hai'), {
    type: ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT,
    payload: { recordId: 'SYN-002', field: 'age', value: '44' },
  })
  assert.deepEqual(parseAssistantCommand('Record SYN-002 name to Asha'), {
    type: ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT,
    payload: { recordId: 'SYN-002', field: 'name', value: 'Asha' },
  })
})

test('parses recheck, export, counterfactual, history, undo, and clear commands', () => {
  assert.equal(parseAssistantCommand('Is finding ko dobara check karo', 'FND-1').type, ASSISTANT_ACTIONS.RECHECK_FINDING)
  assert.deepEqual(parseAssistantCommand('Findings ka report download karo'), {
    type: ASSISTANT_ACTIONS.EXPORT_REPORT,
    payload: { reportType: 'findings' },
  })
  assert.deepEqual(parseAssistantCommand('Agar threshold 20% kar dein toh?'), {
    type: ASSISTANT_ACTIONS.RUN_COUNTERFACTUAL,
    payload: { threshold: 20, areaId: undefined },
  })
  assert.equal(parseAssistantCommand('show change history').type, ASSISTANT_ACTIONS.SHOW_CHANGE_HISTORY)
  assert.equal(parseAssistantCommand('clear chat').type, ASSISTANT_ACTIONS.CLEAR_CHAT)
  assert.equal(parseAssistantCommand('undo last change').type, ASSISTANT_ACTIONS.UNDO_RECORD_EDIT)
  assert.equal(parseAssistantCommand('Download revised draft CSV').type, ASSISTANT_ACTIONS.EXPORT_DRAFT)
  assert.deepEqual(parseAssistantCommand('B01 ka comparison doosre areas se karo'), {
    type: ASSISTANT_ACTIONS.COMPARE_AREA,
    payload: { areaId: 'B01' },
  })
})

test('rejects unsupported, invalid, and context-free actions', () => {
  assert.equal(validateAssistantAction({ type: 'call_any_url' }, { analysis }).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.INSPECT_RECORD, payload: { recordId: 'SYN-1' } }, {}).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.PROPOSE_RECORD_EDIT, payload: { recordId: 'SYN-1', field: 'age', value: '121' } }, { analysis }).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.EXPORT_REPORT, payload: { reportType: 'pdf' } }, { analysis }).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.OPEN_EVIDENCE }, { analysis }).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.EXPORT_DRAFT }, { analysis, hasConfirmedDraft: false }).valid, false)
  assert.equal(validateAssistantAction({ type: ASSISTANT_ACTIONS.EXPORT_DRAFT }, { analysis, hasConfirmedDraft: true }).valid, true)
})

test('selects highest priority deterministically without claiming severity', () => {
  const findings = [
    { finding_id: 'FND-2', review_priority: 'MEDIUM' },
    { finding_id: 'FND-3', review_priority: 'HIGH' },
    { finding_id: 'FND-1', review_priority: 'HIGH' },
  ]
  assert.equal(highestFinding(findings).finding_id, 'FND-1')
})

test('draft CSV round trip preserves originals and quoted values', () => {
  const original = 'record_id,name,age\nSYN-002,"Asha, Rao",43\n'
  const rows = parseCsv(original)
  rows[0].age = '44'
  const draft = serializeCsv(rows)
  assert.equal(parseCsv(original)[0].age, '43')
  assert.equal(parseCsv(draft)[0].name, 'Asha, Rao')
  assert.equal(parseCsv(draft)[0].age, '44')
  assert.match(serializeCsv([{ record_id: 'A', first: 'x' }, { record_id: 'B', later_column: 'y' }]), /later_column/)
})

test('draft edits copy rows, reject unknown IDs, and reject duplicate IDs', () => {
  const original = [{ record_id: 'SYN-002', age: '43' }]
  const changed = applyDraftChange(original, { recordId: 'SYN-002', field: 'age', value: '44' })
  assert.equal(original[0].age, '43')
  assert.equal(changed.rows[0].age, '44')
  assert.throws(() => resolveDraftRecord(original, 'UNKNOWN'), /not found/)
  assert.throws(() => resolveDraftRecord([...original, { record_id: 'SYN-002', age: '45' }], 'SYN-002'), /duplicated/)
})
