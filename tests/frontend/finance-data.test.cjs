const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const validation = require('../../frontend/finance-validation.js');
const finance = require('../../frontend/finance-engine.js');
const context = { window: {}, structuredClone, Intl };
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/fixtures.js', 'utf8'), context);
const ledger = () => structuredClone(context.window.StillHereFixtures.emptySnapshot.finance.ledger);
const input = () => ({ ledger: ledger(), start_date: '2026-10-10', case_time_zone: 'America/Chicago', input_case_version: 3 });
const expense = { operation: 'record_expense', event_id: 'spend', effective_date: '2026-10-10', money_source_id: 'cash_demo_001', amount_cents: 200, category: 'food', commitment_id: 'food_daily', balance_effect: 'adjust_source' };

test('fixture and calculated baseline/scenarios satisfy the complete data contracts', () => {
  const request = { ...input(), scenarios: finance.scenarios.slice(1) };
  assert.equal(validation.validateLedger(request.ledger), true);
  assert.equal(validation.validateForecastInput(request), true);
  const before = JSON.stringify(request);
  const result = finance.forecast_finances(request);
  assert.equal(validation.validateForecastOutput(result), true);
  assert.equal(result.baseline.opening_accessible_cents, 30000);
  assert.equal(result.baseline.days.length, 14);
  assert.equal(JSON.stringify(request), before);
});

test('malformed and ambiguous saved ledgers cannot be updated or forecast', () => {
  const cases = [
    (value) => value.money_sources.push(null),
    (value) => value.money_sources.push(structuredClone(value.money_sources[0])),
    (value) => { value.expense_commitments[0].amount_cents = '2000'; },
    (value) => { value.expense_commitments[0].start_day = 14; value.expense_commitments[0].end_day = 1; },
    (value) => { value.money_sources[0].available_on = '2026-10-12'; value.money_sources[0].expires_on = '2026-10-11'; },
    (value) => { value.money_sources[0].reflected_event_ids = ['missing']; },
    (value) => { value.aid = [{ id: 'aid', stage: 'received', amount_cents: 10, actual_receipt_id: 'invented' }]; }
  ];
  for (const change of cases) {
    const value = ledger(); change(value);
    const before = JSON.stringify(value);
    const result = finance.apply_financial_update(value, expense);
    assert.equal(result.status, 'rejected');
    assert.equal(result.issues[0].code, 'invalid_ledger');
    assert.equal(JSON.stringify(value), before);
    assert.throws(() => finance.forecast_finances({ ...input(), ledger: value }), TypeError);
  }
});

test('updated and reversed ledgers retain valid typed audit records', () => {
  const applied = finance.apply_financial_update(ledger(), expense);
  assert.equal(validation.validateUpdateResult(applied), true);
  let value = applied.ledger;
  assert.equal(validation.validateLedger(value), true);
  value = finance.apply_financial_update(value, { operation: 'upsert_commitment', event_id: 'edit', effective_date: '2026-10-10', record: { id: 'food_daily', category: 'food', amount_cents: 2200, start_day: 1, end_day: 14 } }).ledger;
  assert.equal(validation.validateLedger(value), true);
  value = finance.apply_financial_update(value, { operation: 'reverse_record_update', event_id: 'undo_edit', effective_date: '2026-10-10', original_update_id: 'edit' }).ledger;
  value = finance.apply_financial_update(value, { operation: 'reverse_event', event_id: 'undo_spend', effective_date: '2026-10-10', original_event_id: 'spend', balance_effect: 'adjust_source' }).ledger;
  assert.equal(validation.validateLedger(value), true);
  assert.equal(validation.validateForecastOutput(finance.forecast_finances({ ...input(), ledger: value })), true);
});

test('dated scenario coverage and unknown action costs retain validated uncertainty', () => {
  const request = { ...input(), scenarios: [{ id: 'stay', support: [{ categories: ['lodging'], start_date: '2026-10-10', end_date: '2026-10-11', amount_cents: 8000 }], receipts: [] }], action_alternatives: [{ id: 'visit', costs: [{ id: 'fare', category: 'transport', date: '2026-10-12', amount_cents: null }] }] };
  const result = finance.forecast_finances(request);
  assert.equal(result.scenarios[0].days[0].support_cents, 4000);
  assert.equal(result.action_comparisons[0].result.ending_projected_cents, null);
  assert.equal(result.action_comparisons[0].result.days[0].projected_cents, null);
  assert.ok(result.warnings.length);
  assert.equal(validation.validateForecastOutput(result), true);
});

test('forecast contracts reject extra fields, mixed dates, invalid zones and duplicate IDs', () => {
  const scenario = { id: 'one', support: [], receipts: [{ day: 1, date: '2026-10-10', amount_cents: 100 }] };
  const cases = [
    { ...input(), extra: true },
    { ...input(), scenarios: [scenario] },
    { ...input(), case_time_zone: 'invalid/place' },
    { ...input(), scenarios: Array.from({ length: 4 }, (_, i) => ({ id: `s${i}`, support: [], receipts: [] })) },
    { ...input(), action_alternatives: [{ id: 'same', costs: [] }, { id: 'same', costs: [] }] },
    { ...input(), action_alternatives: [{ id: 'visit', costs: [{ id: 'food_daily', category: 'food', date: '2026-10-10', amount_cents: 100 }] }] }
  ];
  for (const request of cases) assert.throws(() => finance.forecast_finances(request), TypeError);
});

test('aggregate overflow is rejected instead of returning imprecise cents', () => {
  const request = input();
  request.ledger.money_sources[0].balance_cents = Number.MAX_SAFE_INTEGER;
  request.ledger.money_sources.push({ ...request.ledger.money_sources[0], id: 'second' });
  assert.throws(() => finance.forecast_finances(request), RangeError);
});

test('allocation prioritizes essential costs and still reports uncovered nonessential costs', () => {
  const request = input();
  request.ledger.money_sources[0].balance_cents = 100;
  request.ledger.expense_commitments = [
    { id: 'a_other', category: 'other', amount_cents: 100, date: '2026-10-10', essential: false },
    { id: 'z_food', category: 'food', amount_cents: 100, date: '2026-10-10', essential: true }
  ];
  const result = finance.forecast_finances(request);
  assert.deepEqual(result.baseline.first_gap.affected_commitment_ids, ['a_other']);
  assert.equal(result.baseline.first_gap.amount_cents, 100);
  assert.equal(result.baseline.days[0].unmet_cents, 100);
});

test('overlapping record and event names do not produce duplicate changed-record IDs', () => {
  const result = finance.apply_financial_update(ledger(), { ...expense, event_id: 'cash_demo_001' });
  assert.equal(result.status, 'applied');
  assert.equal(validation.validateUpdateResult(result), true);
  assert.equal(new Set(result.changed_record_ids).size, result.changed_record_ids.length);
});
// Built by Raneem Mousa
