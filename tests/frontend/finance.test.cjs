const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {}, structuredClone, Intl };
vm.createContext(context);
for (const name of ['fixtures', 'finance-validation', 'finance-engine']) vm.runInContext(fs.readFileSync(`frontend/${name}.js`, 'utf8'), context);
const finance = context.window.StillHereFinance;
const ledger = () => structuredClone(context.window.StillHereFixtures.emptySnapshot.finance.ledger);
const plain = (value) => JSON.parse(JSON.stringify(value));
const expense = { operation: 'record_expense', event_id: 'spend_1', money_source_id: 'cash_demo_001', amount_cents: 1200, effective_date: '2026-10-10', category: 'food', balance_effect: 'adjust_source', commitment_id: 'food_daily' };

test('four required forecasts preserve early gaps and exact final positions', () => {
  const results = finance.compare(ledger(), '2026-10-10');
  assert.deepEqual(plain(results.map((r) => [r.first_gap?.day ?? null, r.first_gap?.amount_cents ?? null, r.ending_projected_cents])), [[5, 5500, -64000], [11, 2500, -22000], [null, null, 28000], [11, 2500, 28000]]);
});
test('actual expense reduces its matching commitment once and leaves input untouched', () => {
  const before = ledger();
  const result = finance.applyFinancialUpdate(before, expense);
  assert.equal(result.status, 'applied');
  assert.equal(before.money_sources[0].balance_cents, 30000);
  assert.equal(result.ledger.money_sources[0].balance_cents, 28800);
  assert.equal(finance.forecast(result.ledger, '2026-10-10').ending_projected_cents, -64000);
  assert.equal(finance.applyFinancialUpdate(result.ledger, expense).status, 'already_applied');
  assert.equal(finance.applyFinancialUpdate(result.ledger, { ...expense, amount_cents: 1300 }).status, 'rejected');
});
test('already reflected spending never deducts the balance a second time', () => {
  const input = ledger(); input.money_sources[0].balance_cents = 28800;
  const result = finance.applyFinancialUpdate(input, { ...expense, balance_effect: 'already_reflected' });
  assert.equal(result.ledger.money_sources[0].balance_cents, 28800);
  assert.equal(finance.forecast(result.ledger, '2026-10-10').ending_projected_cents, -64000);
});
test('confirmed support is capped, overlapping support cannot erase the same expense twice', () => {
  const input = ledger();
  input.support = [{ id: 'a', state: 'confirmed', categories: ['food'], start_day: 1, end_day: 14, amount_cents: 2500 }, { id: 'b', state: 'confirmed', categories: ['food'], start_day: 1, end_day: 1, amount_cents: 2000 }];
  const before = JSON.stringify(input);
  const result = finance.forecast(input, '2026-10-10');
  assert.equal(result.days[0].support_cents, 2000);
  assert.equal(result.days[1].support_cents, 500);
  assert.equal(result.days[2].support_cents, 0);
  assert.equal(JSON.stringify(input), before);
});
test('restricted money pays only eligible expenses after noncash support', () => {
  const input = ledger();
  input.money_sources.push({ id: 'food_voucher', as_of: '2026-10-10', currency: 'USD', accessible: true, balance_cents: 3000, restrictions: ['food'] });
  input.support = [{ id: 'meals', state: 'confirmed', categories: ['food'], start_day: 1, end_day: 1 }];
  const result = finance.forecast(input, '2026-10-10');
  assert.equal(result.opening_cents, 30000);
  assert.equal(result.days[0].restricted_cents, 0);
  assert.equal(result.days[1].restricted_cents, 2000);
  assert.equal(result.days[2].restricted_cents, 1000);
  assert.equal(result.days[3].restricted_cents, 0);
  assert.equal(result.ending_projected_cents, -59000);
});
test('unconfirmed support and unreceived aid never enter baseline', () => {
  const input = ledger();
  input.support = [{ id: 'possible', state: 'hypothetical', categories: ['food'], start_day: 1, end_day: 14 }];
  input.aid = [{ id: 'application', state: 'approved', amount_cents: 50000 }];
  assert.equal(finance.forecast(input, '2026-10-10').ending_projected_cents, -64000);
});
test('unknown costs produce incomplete projections and retain version on alternatives', () => {
  const result = finance.forecastFinances({ ledger: ledger(), start_date: '2026-10-10', case_time_zone: 'America/Chicago', input_case_version: 7, action_alternatives: [{ id: 'visit', costs: [{ id: 'fare', date: '2026-10-11', amount_cents: null }] }] });
  assert.equal(result.baseline.ending_projected_cents, -64000);
  assert.equal(result.action_comparisons[0].result.input_case_version, 7);
  assert.equal(result.action_comparisons[0].result.ending_projected_cents, null);
  assert.ok(result.action_comparisons[0].result.warnings.length);
});
test('duplicate aid receipt asks for reconciliation without changing balances', () => {
  const input = ledger(); input.aid = [{ id: 'aid_1', stage: 'approved', restrictions: [] }];
  const receipt = { operation: 'record_receipt', event_id: 'receipt_1', money_source_id: 'cash_demo_001', amount_cents: 50000, effective_date: '2026-10-10', balance_effect: 'adjust_source', aid_id: 'aid_1' };
  const applied = finance.applyFinancialUpdate(input, receipt);
  const duplicate = finance.applyFinancialUpdate(applied.ledger, { ...receipt, event_id: 'import_1' });
  assert.equal(duplicate.status, 'needs_clarification');
  assert.equal(duplicate.ledger.money_sources[0].balance_cents, 80000);
});


test('balance refresh requires explicit reconciliation and is idempotent', () => {
  const spent = finance.applyFinancialUpdate(ledger(), expense).ledger;
  const update = { operation: 'refresh_balance', event_id: 'balance_2', effective_date: '2026-10-10', money_source_id: 'cash_demo_001', balance_cents: 28800, reflected_event_ids: ['spend_1'] };
  assert.equal(finance.applyFinancialUpdate(spent, { ...update, reflected_event_ids: [] }).status, 'needs_clarification');
  const refreshed = finance.applyFinancialUpdate(spent, update);
  assert.equal(refreshed.status, 'applied');
  assert.equal(refreshed.ledger.money_sources[0].balance_cents, 28800);
  assert.equal(finance.applyFinancialUpdate(refreshed.ledger, update).status, 'already_applied');
  assert.equal(refreshed.ledger.record_updates[0].before.balance_cents, 28800);
});
test('commitment corrections retain paid portions and audit the old record', () => {
  const spent = finance.applyFinancialUpdate(ledger(), expense).ledger;
  const update = { operation: 'upsert_commitment', event_id: 'cost_2', effective_date: '2026-10-10', record: { id: 'food_daily', category: 'food', amount_cents: 2500, start_day: 1, end_day: 14 } };
  const result = finance.applyFinancialUpdate(spent, update);
  assert.equal(result.status, 'applied');
  assert.equal(result.ledger.expense_commitments[0].fulfilled_by_date['2026-10-10'], 1200);
  assert.equal(result.ledger.record_updates[0].before.amount_cents, 2000);
  assert.equal(finance.forecast(result.ledger, '2026-10-10').ending_projected_cents, -71000);
});
test('aid edits cannot manufacture a received payment', () => {
  const update = { operation: 'upsert_aid', event_id: 'aid_update', effective_date: '2026-10-10', record: { id: 'new_aid', stage: 'received', amount_cents: 50000 } };
  assert.equal(finance.applyFinancialUpdate(ledger(), update).status, 'needs_clarification');
  const applied = finance.applyFinancialUpdate(ledger(), { ...update, record: { ...update.record, stage: 'approved' } });
  assert.equal(applied.status, 'applied');
  assert.equal(finance.forecast(applied.ledger, '2026-10-10').opening_cents, 30000);
});
test('support edit enters baseline only after confirmation and retains previous state', () => {
  const update = { operation: 'upsert_support', event_id: 'support_1', effective_date: '2026-10-10', record: { id: 'stay', state: 'hypothetical', categories: ['lodging'], start_day: 1, end_day: 7, amount_cents: 28000 } };
  const proposed = finance.applyFinancialUpdate(ledger(), update);
  assert.equal(finance.forecast(proposed.ledger, '2026-10-10').ending_projected_cents, -64000);
  const confirmed = finance.applyFinancialUpdate(proposed.ledger, { ...update, event_id: 'support_2', record: { ...update.record, state: 'confirmed' } });
  assert.equal(finance.forecast(confirmed.ledger, '2026-10-10').ending_projected_cents, -36000);
  assert.equal(confirmed.ledger.record_updates[1].before.state, 'hypothetical');
});
test('invalid dates and reused record-update IDs are rejected', () => {
  assert.throws(() => finance.forecast(ledger(), '2026-02-30'));
  const update = { operation: 'upsert_money_source', event_id: 'source_add', effective_date: '2026-10-10', record: { id: 'new_cash', balance_cents: 1000, currency: 'USD', accessible: true, restrictions: [], as_of: '2026-10-10' } };
  const added = finance.applyFinancialUpdate(ledger(), update);
  assert.equal(added.status, 'applied');
  assert.equal(finance.applyFinancialUpdate(added.ledger, { ...expense, event_id: 'source_add' }).status, 'rejected');
});


const transferLedger = () => {
  const input = ledger();
  input.money_sources.push({ id: 'bank', type: 'account', balance_cents: 10000, currency: 'USD', accessible: true, restrictions: [], as_of: '2026-10-10' });
  return input;
};
const transfer = { operation: 'record_transfer', event_id: 'transfer_1', effective_date: '2026-10-10', money_source_id: 'bank', destination_source_id: 'cash_demo_001', amount_cents: 2500, balance_effect: 'adjust_source', cash_on_hand_confirmed: true };
test('transfer conserves household money, confirms cash, and replays once', () => {
  const input = transferLedger();
  assert.equal(finance.applyFinancialUpdate(input, { ...transfer, cash_on_hand_confirmed: false }).status, 'needs_clarification');
  const applied = finance.applyFinancialUpdate(input, transfer);
  assert.equal(applied.status, 'applied');
  assert.deepEqual(plain(applied.ledger.money_sources.map((source) => source.balance_cents)), [32500, 7500]);
  assert.equal(finance.forecast(applied.ledger, '2026-10-10').opening_cents, 40000);
  assert.equal(finance.applyFinancialUpdate(applied.ledger, transfer).status, 'already_applied');
  assert.equal(input.actual_events.length, 0);
});
test('transfer cannot turn restricted money into unrestricted cash', () => {
  const input = transferLedger(); input.money_sources[1].restrictions = ['food'];
  const result = finance.applyFinancialUpdate(input, transfer);
  assert.equal(result.status, 'needs_clarification');
  assert.equal(result.ledger.money_sources[1].balance_cents, 10000);
});
test('expense reversal restores cash and commitment while preserving original event', () => {
  const applied = finance.applyFinancialUpdate(ledger(), expense);
  const reversal = { operation: 'reverse_event', event_id: 'reverse_1', original_event_id: 'spend_1', effective_date: '2026-10-10', balance_effect: 'adjust_source' };
  const reversed = finance.applyFinancialUpdate(applied.ledger, reversal);
  assert.equal(reversed.status, 'applied');
  assert.equal(reversed.ledger.money_sources[0].balance_cents, 30000);
  assert.equal(reversed.ledger.expense_commitments[0].fulfilled_by_date['2026-10-10'], 0);
  assert.equal(reversed.ledger.actual_events[0].reversed_by, 'reverse_1');
  assert.equal(applied.ledger.actual_events[0].reversed_by, undefined);
  assert.equal(finance.applyFinancialUpdate(reversed.ledger, reversal).status, 'already_applied');
  assert.equal(finance.applyFinancialUpdate(reversed.ledger, expense).status, 'already_applied');
  assert.equal(finance.forecast(reversed.ledger, '2026-10-10').ending_projected_cents, -64000);
});
test('transfer reversal affects both sources and refresh must acknowledge destination events', () => {
  const applied = finance.applyFinancialUpdate(transferLedger(), transfer);
  const reversal = { operation: 'reverse_event', event_id: 'reverse_transfer', original_event_id: 'transfer_1', effective_date: '2026-10-10', balance_effect: 'adjust_source' };
  const reversed = finance.applyFinancialUpdate(applied.ledger, reversal);
  assert.deepEqual(plain(reversed.ledger.money_sources.map((source) => source.balance_cents)), [30000, 10000]);
  const refresh = { operation: 'refresh_balance', event_id: 'refresh_cash', effective_date: '2026-10-10', money_source_id: 'cash_demo_001', balance_cents: 30000, reflected_event_ids: [] };
  assert.equal(finance.applyFinancialUpdate(reversed.ledger, refresh).status, 'needs_clarification');
  assert.equal(finance.applyFinancialUpdate(reversed.ledger, { ...refresh, reflected_event_ids: ['transfer_1', 'reverse_transfer'] }).status, 'applied');
});
test('receipt reversal restores aid stage and rejects impossible balances atomically', () => {
  const input = ledger(); input.aid = [{ id: 'aid', stage: 'approved', amount_cents: 5000, restrictions: [] }];
  const receipt = { operation: 'record_receipt', event_id: 'receipt', money_source_id: 'cash_demo_001', effective_date: '2026-10-10', amount_cents: 5000, balance_effect: 'adjust_source', aid_id: 'aid' };
  const applied = finance.applyFinancialUpdate(input, receipt);
  const reversal = { operation: 'reverse_event', event_id: 'undo_receipt', original_event_id: 'receipt', effective_date: '2026-10-10', balance_effect: 'adjust_source' };
  const reversed = finance.applyFinancialUpdate(applied.ledger, reversal);
  assert.equal(reversed.ledger.aid[0].stage, 'approved');
  assert.equal(reversed.ledger.aid[0].actual_receipt_id, undefined);
  assert.equal(finance.applyFinancialUpdate(reversed.ledger, { ...receipt, event_id: 'correct_receipt', amount_cents: 4500 }).status, 'applied');
  const low = structuredClone(applied.ledger); low.money_sources[0].balance_cents = 100;
  const rejected = finance.applyFinancialUpdate(low, reversal);
  assert.equal(rejected.status, 'needs_clarification');
  assert.equal(rejected.ledger.actual_events[0].reversed_by, undefined);
  assert.equal(rejected.ledger.aid[0].stage, 'received');
});

test('received aid edits retain their derived receipt link and remain reversible', () => {
  const input = ledger(); input.aid = [{ id: 'aid', stage: 'approved', amount_cents: 5000, restrictions: [] }];
  const receipt = { operation: 'record_receipt', event_id: 'receipt', money_source_id: 'cash_demo_001', effective_date: '2026-10-10', amount_cents: 5000, balance_effect: 'adjust_source', aid_id: 'aid' };
  const received = finance.applyFinancialUpdate(input, receipt);
  const edit = { operation: 'upsert_aid', event_id: 'aid_edit', effective_date: '2026-10-10', record: { id: 'aid', stage: 'received', amount_cents: 5000, restrictions: [], evidence_ids: ['user_confirmation'] } };
  const edited = finance.applyFinancialUpdate(received.ledger, edit);
  assert.equal(edited.status, 'applied');
  assert.equal(edited.ledger.aid[0].actual_receipt_id, 'receipt');
  const reversed = finance.applyFinancialUpdate(edited.ledger, { operation: 'reverse_event', event_id: 'undo_receipt', original_event_id: 'receipt', effective_date: '2026-10-10', balance_effect: 'adjust_source' });
  assert.equal(reversed.status, 'applied');
  assert.equal(reversed.ledger.aid[0].stage, 'approved');
  assert.equal(reversed.ledger.money_sources[0].balance_cents, 30000);
});

test('received aid cannot be marked unreceived while its receipt remains active', () => {
  const input = ledger(); input.aid = [{ id: 'aid', stage: 'approved', amount_cents: 5000, restrictions: [] }];
  const received = finance.applyFinancialUpdate(input, { operation: 'record_receipt', event_id: 'receipt', money_source_id: 'cash_demo_001', effective_date: '2026-10-10', amount_cents: 5000, balance_effect: 'adjust_source', aid_id: 'aid' });
  const result = finance.applyFinancialUpdate(received.ledger, { operation: 'upsert_aid', event_id: 'aid_edit', effective_date: '2026-10-10', record: { id: 'aid', stage: 'approved', amount_cents: 5000, restrictions: [] } });
  assert.equal(result.status, 'needs_clarification');
  assert.equal(result.issues[0].code, 'receipt_reversal_required');
  assert.equal(result.ledger, received.ledger);
});


test('unknown aid restrictions and ambiguous planned spending require clarification', () => {
  const input = ledger(); input.aid = [{ id: 'unknown_terms', stage: 'approved' }];
  const receipt = { operation: 'record_receipt', event_id: 'terms', money_source_id: 'cash_demo_001', effective_date: '2026-10-10', amount_cents: 5000, balance_effect: 'adjust_source', aid_id: 'unknown_terms' };
  assert.equal(finance.applyFinancialUpdate(input, receipt).status, 'needs_clarification');
  const unlinked = { ...expense }; delete unlinked.commitment_id;
  assert.equal(finance.applyFinancialUpdate(input, unlinked).status, 'needs_clarification');
  assert.equal(finance.applyFinancialUpdate(input, { ...unlinked, unplanned: true }).status, 'applied');
  input.money_sources[0].restrictions = ['transport'];
  assert.equal(finance.applyFinancialUpdate(input, expense).status, 'needs_clarification');
});
test('restriction expiry cannot disappear in a transfer', () => {
  const input = transferLedger();
  input.money_sources[1].expires_on = '2026-10-11';
  assert.equal(finance.applyFinancialUpdate(input, transfer).status, 'needs_clarification');
});


test('source access edits preserve money, require evidence for restrictions, and undo', () => {
  const input = ledger();
  const edit = { operation: 'set_source_access', event_id: 'access_1', effective_date: '2026-10-10', money_source_id: 'cash_demo_001', accessible: false, restrictions: [] };
  const applied = finance.applyFinancialUpdate(input, edit);
  assert.equal(applied.status, 'applied');
  assert.equal(applied.ledger.money_sources[0].balance_cents, 30000);
  assert.equal(finance.forecast(applied.ledger, '2026-10-10').opening_cents, 0);
  const undo = { operation: 'reverse_record_update', event_id: 'undo_access', effective_date: '2026-10-10', original_update_id: 'access_1' };
  const restored = finance.applyFinancialUpdate(applied.ledger, undo);
  assert.equal(restored.status, 'applied');
  assert.equal(finance.forecast(restored.ledger, '2026-10-10').opening_cents, 30000);
  assert.equal(finance.applyFinancialUpdate(restored.ledger, undo).status, 'already_applied');
  assert.equal(finance.applyFinancialUpdate(input, { ...edit, restrictions: ['food'] }).status, 'needs_clarification');
  assert.equal(finance.applyFinancialUpdate(input, { ...edit, restrictions: ['food'], evidence_ids: ['user_report_1'] }).status, 'applied');
});
test('undo refuses to overwrite later spending and retains both audits', () => {
  const edit = { operation: 'set_source_access', event_id: 'access_1', effective_date: '2026-10-10', money_source_id: 'cash_demo_001', accessible: true, restrictions: [] };
  const applied = finance.applyFinancialUpdate(ledger(), edit);
  const spent = finance.applyFinancialUpdate(applied.ledger, expense);
  const undo = { operation: 'reverse_record_update', event_id: 'undo_access', effective_date: '2026-10-10', original_update_id: 'access_1' };
  const refused = finance.applyFinancialUpdate(spent.ledger, undo);
  assert.equal(refused.status, 'needs_clarification');
  assert.equal(refused.ledger.money_sources[0].balance_cents, 28800);
  assert.equal(refused.ledger.record_updates[0].reversed_by, undefined);
});
test('record undo restores previous commitment or removes an unused added record', () => {
  const edit = { operation: 'upsert_commitment', event_id: 'cost_edit', effective_date: '2026-10-10', record: { id: 'food_daily', category: 'food', amount_cents: 3000, day: 1 } };
  const applied = finance.applyFinancialUpdate(ledger(), edit);
  const undo = { operation: 'reverse_record_update', event_id: 'undo_cost', effective_date: '2026-10-10', original_update_id: 'cost_edit' };
  const restored = finance.applyFinancialUpdate(applied.ledger, undo);
  assert.equal(restored.ledger.expense_commitments[0].amount_cents, 2000);
  const added = finance.applyFinancialUpdate(ledger(), { ...edit, record: { ...edit.record, id: 'new_cost' } });
  const removed = finance.applyFinancialUpdate(added.ledger, undo);
  assert.equal(removed.status, 'applied');
  assert.ok(!removed.ledger.expense_commitments.some((item) => item.id === 'new_cost'));
});


test('dated availability and expiry change usable cash on the right day', () => {
  const future = ledger(); future.money_sources[0].available_on = '2026-10-11';
  const delayed = finance.forecast(future, '2026-10-10');
  assert.equal(delayed.opening_cents, 0);
  assert.equal(delayed.first_gap.day, 1);
  assert.equal(delayed.days[1].released_cents, 30000);
  assert.equal(delayed.ending_projected_cents, -64000);
  const expiring = ledger(); expiring.money_sources[0].expires_on = '2026-10-10';
  const expired = finance.forecast(expiring, '2026-10-10');
  assert.equal(expired.days[1].expired_cents, 20500);
  assert.equal(expired.first_gap.day, 2);
  assert.equal(expired.first_gap.amount_cents, 6500);
});
test('after-expense receipts preserve a same-day gap while before-expense receipts cover it', () => {
  const input = ledger(); input.money_sources[0].balance_cents = 5000;
  input.expense_commitments = [{ id: 'rent', category: 'lodging', amount_cents: 10000, date: '2026-10-10' }];
  const scenario = { id: 'dated', support: [], receipts: [{ amount_cents: 5000, date: '2026-10-10', timing: 'after_expenses' }] };
  const late = finance.forecastFinances({ ledger: input, start_date: '2026-10-10', case_time_zone: 'America/Chicago', scenarios: [scenario] }).scenarios[0];
  assert.equal(late.first_gap.amount_cents, 5000);
  assert.equal(late.ending_projected_cents, 0);
  scenario.receipts[0].timing = 'before_expenses';
  const early = finance.forecast(input, '2026-10-10', scenario);
  assert.equal(early.first_gap, null);
  assert.equal(early.ending_projected_cents, 0);
});
test('stale balances are incomplete and calendar costs do not shift on a later start', () => {
  const input = ledger(); input.expense_commitments = [{ id: 'once', category: 'food', amount_cents: 1000, date: '2026-10-10' }];
  const stale = finance.forecast(input, '2026-10-11');
  assert.equal(stale.ending_projected_cents, null);
  assert.ok(stale.warnings.some((warning) => warning.includes('needs confirmation')));
  input.money_sources[0].as_of = '2026-10-11';
  const current = finance.forecast(input, '2026-10-11');
  assert.equal(current.ending_projected_cents, 30000);
});
// Built by Raneem Mousa
