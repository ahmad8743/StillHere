const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Ajv = require('ajv/dist/2020');
const schema = require('../../contracts/finance-update.schema.json');
const { validateUpdate } = require('../../frontend/finance-validation.js');
const finance = require('../../frontend/finance-engine.js');

function browser(includeValidator = true) {
  const context = { window: {}, structuredClone, Intl };
  vm.createContext(context);
  const files = ['fixtures', ...(includeValidator ? ['finance-validation'] : []), 'finance-engine'];
  for (const file of files) vm.runInContext(fs.readFileSync(`frontend/${file}.js`, 'utf8'), context);
  return context.window;
}
const window = browser();
const ledger = () => structuredClone(window.StillHereFixtures.emptySnapshot.finance.ledger);
const plain = (value) => JSON.parse(JSON.stringify(value));
const envelope = { event_id: 'contract_1', effective_date: '2026-10-10' };
const expense = { ...envelope, operation: 'record_expense', money_source_id: 'cash_demo_001', amount_cents: 1200, category: 'food', commitment_id: 'food_daily', balance_effect: 'adjust_source' };
const updates = [
  expense,
  { ...envelope, operation: 'record_receipt', money_source_id: 'cash_demo_001', amount_cents: 5000, balance_effect: 'adjust_source' },
  { ...envelope, operation: 'record_transfer', money_source_id: 'cash_demo_001', destination_source_id: 'account_2', amount_cents: 5000, balance_effect: 'adjust_source' },
  { ...envelope, operation: 'reverse_event', original_event_id: 'original_1', balance_effect: 'adjust_source' },
  { ...envelope, operation: 'refresh_balance', money_source_id: 'cash_demo_001', balance_cents: 30000, reflected_event_ids: [] },
  { ...envelope, operation: 'upsert_money_source', record: { id: 'account_2', balance_cents: null, currency: 'USD', accessible: false, restrictions: null, as_of: '2026-10-10' } },
  { ...envelope, operation: 'upsert_commitment', record: { id: 'fare', category: 'transport', amount_cents: null, date: '2026-10-12' } },
  { ...envelope, operation: 'upsert_aid', record: { id: 'award', stage: 'approved', amount_cents: 50000, restrictions: [] } },
  { ...envelope, operation: 'upsert_support', record: { id: 'stay', state: 'confirmed', categories: ['lodging'], start_day: 1, end_day: 7 } },
  { ...envelope, operation: 'set_source_access', money_source_id: 'cash_demo_001', accessible: false, restrictions: [] },
  { ...envelope, operation: 'reverse_record_update', original_update_id: 'original_1' }
];
const ajv = new Ajv({ strict: false, allErrors: true });
ajv.addFormat('date', (value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value);
const validateSchema = ajv.compile(schema);

test('generated Node and browser validators accept every supported operation like AJV', () => {
  assert.equal(updates.length, schema.oneOf.length);
  for (const update of updates) {
    const before = JSON.stringify(update);
    assert.equal(validateSchema(update), true, update.operation);
    assert.equal(validateUpdate(update), true, update.operation);
    assert.equal(window.StillHereFinanceValidation.validateUpdate(update), true, update.operation);
    assert.equal(JSON.stringify(update), before);
  }
});

test('malformed updates are rejected before changing or auditing money', () => {
  const { balance_effect, ...missingBalanceEffect } = expense;
  const malformed = [
    null, [], {}, missingBalanceEffect,
    { ...expense, operation: 'invent_income' },
    { ...expense, extra: 'unexpected' },
    { ...expense, amount_cents: '1200' },
    { ...expense, amount_cents: 1.5 },
    { ...expense, amount_cents: -1 },
    { ...expense, amount_cents: 0 },
    { ...expense, amount_cents: Number.MAX_SAFE_INTEGER + 1 },
    { ...expense, effective_date: '2026-02-30' },
    { ...expense, event_id: '' },
    { ...expense, unplanned: 'yes' },
    { ...updates[4], reflected_event_ids: ['same', 'same'] },
    { ...updates[5], record: { ...updates[5].record, currency: 'EUR' } },
    { ...updates[7], record: { ...updates[7].record, actual_receipt_id: 'untrusted' } },
    { ...updates[8], record: { ...updates[8].record, categories: ['food', 'food'] } }
  ];
  for (const update of malformed) {
    assert.equal(validateSchema(update), false);
    assert.equal(validateUpdate(update), false);
    const input = ledger();
    const before = JSON.stringify(input);
    for (const engine of [finance, window.StillHereFinance]) {
      const result = engine.applyFinancialUpdate(input, update);
      assert.equal(result.status, 'rejected');
      assert.equal(result.issues[0].code, 'invalid_update');
      assert.equal(result.ledger, input);
      assert.equal(JSON.stringify(input), before);
    }
  }
});

test('calendar validation respects leap years and rejects timestamps or rolled dates', () => {
  for (const [date, expected] of [['2028-02-29', true], ['2026-02-29', false], ['2026-04-31', false], ['2026-13-01', false], ['2026-10-10T00:00:00Z', false]]) {
    const update = { ...expense, effective_date: date };
    assert.equal(validateSchema(update), expected, date);
    assert.equal(validateUpdate(update), expected, date);
    assert.equal(window.StillHereFinanceValidation.validateUpdate(update), expected, date);
  }
});

test('commitment and support schedules require exactly one complete schedule', () => {
  const schedules = [
    [{ date: '2026-10-10' }, true],
    [{ start_date: '2026-10-10', end_date: '2026-10-12' }, true],
    [{ day: 1 }, true],
    [{ start_day: 1, end_day: 14 }, true],
    [{}, false], [{ start_day: 1 }, false], [{ end_date: '2026-10-12' }, false],
    [{ date: '2026-10-10', day: 1 }, false], [{ start_day: 0, end_day: 14 }, false]
  ];
  for (const operation of ['upsert_commitment', 'upsert_support']) {
    const record = operation === 'upsert_commitment'
      ? { id: 'scheduled', category: 'food', amount_cents: 1200 }
      : { id: 'scheduled', state: 'confirmed', categories: ['food'] };
    for (const [schedule, expected] of schedules) {
      const update = { ...envelope, operation, record: { ...record, ...schedule } };
      assert.equal(validateSchema(update), expected);
      assert.equal(validateUpdate(update), expected);
      assert.equal(window.StillHereFinanceValidation.validateUpdate(update), expected);
    }
  }
});

test('browser and Node finance operations return the same results without mutating inputs', () => {
  for (const update of updates) {
    const input = ledger();
    const before = JSON.stringify(input);
    assert.deepEqual(plain(window.StillHereFinance.applyFinancialUpdate(input, update)), plain(finance.applyFinancialUpdate(input, update)), update.operation);
    assert.equal(JSON.stringify(input), before);
  }
});

test('missing browser validator prevents financial writes', () => {
  const unavailable = browser(false).StillHereFinance;
  const input = ledger();
  const result = unavailable.applyFinancialUpdate(input, expense);
  assert.equal(result.status, 'rejected');
  assert.equal(result.issues[0].code, 'validator_unavailable');
  assert.equal(result.ledger, input);
});

test('page loads its local validator before its finance engine', () => {
  const html = fs.readFileSync('frontend/index.html', 'utf8');
  const scripts = [...html.matchAll(/<script\b[^>]*src="([^"]+)"[^>]*>/g)].map((match) => match[1].replace(/^\.\//, ''));
  assert.ok(scripts.indexOf('finance-validation.js') >= 0);
  assert.ok(scripts.indexOf('finance-engine.js') > scripts.indexOf('finance-validation.js'));
});
// Built by Raneem Mousa
