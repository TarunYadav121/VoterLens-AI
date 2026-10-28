import test from 'node:test'
import assert from 'node:assert/strict'

import { parseAssistantCommand, validateAssistantAction, ASSISTANT_ACTIONS } from '../../src/assistant/actions.js'
import { reconcileCounts } from '../../src/utils/audit.js'

test('audit assistant exposes only deterministic supported actions', () => {
  assert.equal(parseAssistantCommand('show findings').type, ASSISTANT_ACTIONS.SHOW_FINDINGS)
  assert.equal(parseAssistantCommand('tell me who committed fraud'), null)
  assert.equal(
    validateAssistantAction({ type: ASSISTANT_ACTIONS.SHOW_FINDINGS }, { analysis: null }).valid,
    true,
  )
})

test('audit count reconciliation detects inconsistent backend totals', () => {
  const result = reconcileCounts({
    previous_records: 4,
    current_records: 5,
    deleted: 1,
    modified: 1,
    unchanged: 2,
    added: 1,
    ambiguous_previous: 0,
    ambiguous_current: 0,
  })
  assert.equal(result.previousPass, true)
  assert.equal(result.currentPass, false)
  assert.equal(result.passed, false)
})
