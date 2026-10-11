const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const controls = require('../../frontend/finance-controls.js');

function demo() {
  const saved = new Map();
  let failSave = false;
  const context = { window: {}, structuredClone, Intl, localStorage: { getItem: (key) => saved.get(key) || null, setItem: (key, value) => { if (failSave) throw new Error('storage full'); saved.set(key, value); } } };
  vm.createContext(context);
  for (const file of ['fixtures', 'finance-validation', 'finance-engine', 'mock-service']) vm.runInContext(fs.readFileSync(`frontend/${file}.js`, 'utf8'), context);
  return { service: context.window.StillHereMockService, fail: (value) => { failSave = value; }, saved, context };
}
function command(service, update) {
  const { event_id, ...payload } = update;
  const snapshot = service.readCase();
  return { contract_version: '0.1', case_id: snapshot.case_id, event_id, expected_case_version: snapshot.case_version, occurred_at: '2026-10-10T15:00:00Z', channel: 'dashboard', type: 'finance.update', payload };
}
const fields = { mode: 'expense', source: 'cash_demo_001', amount: '18.50', date: '2026-10-10', category: 'food', commitment: 'food_daily', balance_effect: 'adjust_source' };

test('dollar entry uses exact cents and rejects malformed or excessive amounts', () => {
  assert.equal(controls.parseMoney('18.50'), 1850);
  assert.equal(controls.parseMoney('0.01'), 1);
  assert.equal(controls.parseMoney('', true), null);
  for (const value of ['', '18.501', '-1', '1e3', 'NaN', '$18', '90071992547410']) assert.throws(() => controls.parseMoney(value), TypeError);
});

test('manual spending updates the shared case once, persists and recalculates', () => {
  const { service, saved, context } = demo();
  const before = service.readCase();
  const update = controls.buildUpdate(before.finance.ledger, fields, 'spend');
  assert.equal(before.finance.ledger.money_sources[0].balance_cents, 30000);
  const request = command(service, update);
  const result = service.submit(request);
  assert.equal(result.status, 'applied');
  assert.equal(result.case_snapshot.case_version, 2);
  assert.equal(result.case_snapshot.finance.ledger.money_sources[0].balance_cents, 28150);
  assert.equal(result.case_snapshot.finance.baseline.ending_projected_cents, -64000);
  assert.equal(result.case_snapshot.finance.input_case_version, 2);
  assert.equal(result.case_snapshot.conversation.turns.length, 0);
  assert.equal(service.submit(request).status, 'already_applied');
  assert.equal(service.readCase().case_version, 2);
  assert.equal(JSON.parse(saved.get('stillhere.p2.mock-case.v1')).case_snapshot.case_version, 2);
  vm.runInContext(fs.readFileSync('frontend/mock-service.js', 'utf8'), context);
  assert.equal(context.window.StillHereMockService.readCase().finance.ledger.money_sources[0].balance_cents, 28150);
});

test('failed device save preserves the case and retry keeps the same event ID', () => {
  const { service, fail } = demo();
  const request = command(service, controls.buildUpdate(service.readCase().finance.ledger, fields, 'spend'));
  const before = JSON.stringify(service.readCase());
  fail(true);
  assert.equal(service.submit(request).status, 'unavailable');
  assert.equal(JSON.stringify(service.readCase()), before);
  fail(false);
  assert.equal(service.submit(request).status, 'applied');
  assert.equal(service.submit(request).status, 'already_applied');
});

test('balance refresh includes both-sided events and undo uses the audited operation', () => {
  const { service } = demo();
  service.submit(command(service, controls.buildUpdate(service.readCase().finance.ledger, fields, 'spend')));
  const ledger = service.readCase().finance.ledger;
  const refresh = controls.buildUpdate(ledger, { mode: 'balance', source: 'cash_demo_001', amount: '281.50', date: '2026-10-10' }, 'refresh');
  assert.deepEqual(Array.from(refresh.reflected_event_ids), ['spend']);
  assert.match(controls.describe(refresh, ledger), /already includes all 1 recorded/);
  assert.equal(service.submit(command(service, refresh)).status, 'applied');
  const undo = controls.buildUpdate(service.readCase().finance.ledger, { mode: 'undo', record: 'spend', date: '2026-10-10' }, 'undo');
  assert.equal(service.submit(command(service, undo)).status, 'applied');
  assert.equal(service.readCase().finance.ledger.money_sources[0].balance_cents, 30000);
});

test('aid approval adds no cash, a linked receipt adds it once and undo restores approval', () => {
  const { service } = demo();
  const aid = controls.buildUpdate(service.readCase().finance.ledger, { mode: 'aid', amount: '50', stage: 'approved', restrictions: '', date: '2026-10-10' }, 'aid');
  assert.equal(service.submit(command(service, aid)).status, 'applied');
  assert.equal(service.readCase().finance.ledger.money_sources[0].balance_cents, 30000);
  const receipt = controls.buildUpdate(service.readCase().finance.ledger, { ...fields, mode: 'receipt', amount: '50', aid: 'aid_aid' }, 'receipt');
  assert.equal(service.submit(command(service, receipt)).status, 'applied');
  assert.equal(service.readCase().finance.ledger.money_sources[0].balance_cents, 35000);
  const undo = controls.buildUpdate(service.readCase().finance.ledger, { mode: 'undo', record: 'receipt', date: '2026-10-10' }, 'undo_receipt');
  assert.equal(service.submit(command(service, undo)).status, 'applied');
  assert.equal(service.readCase().finance.ledger.aid[0].stage, 'approved');
});

test('unknown planned costs and access changes produce honest projections', () => {
  const { service } = demo();
  const cost = controls.buildUpdate(service.readCase().finance.ledger, { mode: 'commitment', amount: '', date: '2026-10-10', category: 'transport', frequency: 'once' }, 'cost');
  assert.equal(service.submit(command(service, cost)).status, 'applied');
  assert.equal(service.readCase().finance.baseline.ending_projected_cents, null);
  const access = controls.buildUpdate(service.readCase().finance.ledger, { mode: 'access', source: 'cash_demo_001', date: '2026-10-10' }, 'access');
  assert.equal(service.submit(command(service, access)).status, 'applied');
  assert.equal(service.readCase().finance.ledger.money_sources[0].balance_cents, 30000);
  assert.equal(service.readCase().finance.baseline.opening_cents, 0);
});

test('changed versions and competing event IDs cannot overwrite financial state', () => {
  const { service } = demo();
  const request = command(service, controls.buildUpdate(service.readCase().finance.ledger, fields, 'spend'));
  const competing = { ...request, payload: { ...request.payload, event_id: 'other' } };
  assert.equal(service.submit(competing).status, 'rejected');
  assert.equal(service.submit(request).status, 'applied');
  assert.equal(service.submit({ ...request, event_id: 'late' }).status, 'conflict');
  assert.equal(service.submit({ ...request, payload: { ...request.payload, amount_cents: 100 } }).status, 'rejected');
  assert.equal(service.readCase().finance.ledger.money_sources[0].balance_cents, 28150);
});
// Built by Raneem Mousa
