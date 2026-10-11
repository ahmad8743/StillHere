# P2 finance handoff

Status: C08 manual module is ready for P1 integration. Schemas remain a proposed `0.1-draft` until both owners freeze them. Evidence covers the independent module and browser-local command adapter, not P1 backend integration.

## Entry points

`frontend/finance-engine.js` has no database, model or network dependency. In Node:

```js
const { apply_financial_update, forecast_finances } = require('./frontend/finance-engine.js');
```

The browser receives the same functions through `window.StillHereFinance`. Inputs are not mutated. Persist only the proposed `result.ledger` of an `applied` result. Other statuses are `already_applied`, `needs_clarification`, and `rejected`. Financial record edits preserve their prior record in `ledger.record_updates`; transactions and reversals remain in `ledger.actual_events`.

JSON Schema 2020-12 contracts:

- `contracts/finance-update.schema.json`: the 11 proposed update operations.
- `contracts/finance-ledger.schema.json`: balances, actual events, commitments, aid, support, prior/next record audits, and `$defs/UpdateResult`.
- `contracts/finance-forecast.schema.json`: `$defs/Input`, `$defs/Output`, individual projections, scenarios, and action costs.

AJV 8.20.0 compiles these into the checked-in `frontend/finance-validation.js`. The module validates ledger/update/forecast inputs and calculated outputs in both Node and the browser. Required/unknown fields, safe integer cents, real calendar dates, unique lists, and exactly one complete schedule are enforced. Domain checks add ID uniqueness, references, date ordering, receipt reconciliation and bounded arithmetic. Invalid ledgers cannot be updated or forecast; unknown valid amounts remain `null` and yield incomplete projections. Rejected invalid inputs are never safe to persist, even when returned unchanged for diagnosis. Load the local validator before the engine; missing validation prevents updates. No third-party runtime package or network request is needed. The contracts have not been merged into P1's case command schema; P1's limited validator must not silently accept unsupported keywords. Future input fields require explicit schema and normalization changes.

## Command mapping

The P1 wrapper must authorize the case and check its version before applying an update. Inject `event_id` from the existing command envelope; do not accept a second competing event ID from a model payload. Map a typed event's date to `effective_date` using the case time zone; do not substitute the server's current date for a user-reported historical date. The older command illustration's `expense_date` maps to this field. Preserve the exact domain request for replay. P1 commits the proposed ledger, audit, and refreshed derived results atomically through its case service.

```js
const request = {
  operation: 'record_expense',
  event_id: 'demo_food_spend_1',
  effective_date: '2026-10-10',
  money_source_id: 'cash_demo_001',
  amount_cents: 1200,
  category: 'food',
  commitment_id: 'food_daily',
  balance_effect: 'adjust_source'
};
const result = apply_financial_update(authorizedSnapshot.finance.ledger, request);
```

`adjust_source` changes the current source balance. `already_reflected` records a transaction whose financial effect is already in that balance. This choice must come from reconciled source information or explicit user clarification.

## Operations

- `record_expense`: positive cents, source, category, date and balance effect. A matching commitment is fulfilled on the expense date. If same-category commitments exist, an unlinked cost requires clarification unless explicitly `unplanned: true`.
- `record_receipt`: positive cents, source, date and balance effect; optional `aid_id`. Aid-linked receipts require known compatible restrictions. A matching receipt updates the aid stage; another receipt for that aid requires clarification.
- `record_transfer`: source and destination IDs, positive cents, date and balance effect. Restrictions, availability dates and expiry must be preserved. Withdrawals into cash require `cash_on_hand_confirmed: true`; fees are separate expenses. Transfers never add income.
- `reverse_event`: original transaction ID, date and explicit balance effect. Restores expense fulfillment or aid status as applicable, retains the original event with `reversed_by`, and appends a correction. Inconsistent balances or references require clarification. Correct an amount by reversing the original and recording the replacement under a new ID; the UI must show these as distinct operations unless a future wrapper supports an atomic combined correction.
- `refresh_balance`: source ID, current cents, date and `reflected_event_ids`. Both sides of a transfer count as affected sources. Conflicting or stale snapshots return clarification while retaining the original ledger.
- `upsert_money_source`: adds a source; existing balances must use `refresh_balance`. Use `set_source_access` to edit existing-source accessibility/restrictions and optional availability/expiry dates. Changed restrictions require a supporting evidence reference.
- `reverse_record_update`: restore a previous record or remove an unused added record. Requires the current record to exactly match the audited after-state; later changes cause clarification, never silent overwrite.
- `upsert_commitment`, `upsert_aid`, `upsert_support`: typed record replacement with prior-record audit. Commitment edits preserve actual fulfillment. Aid cannot become received without an active receipt. Edits of received aid retain the receipt link; reverse the receipt before changing back to an unreceived stage.

## Forecasts

```js
const result = forecast_finances({
  ledger: authorizedSnapshot.finance.ledger,
  start_date: '2026-10-10',
  case_time_zone: 'America/Chicago',
  input_case_version: authorizedSnapshot.case_version,
  scenarios: [],
  action_alternatives: []
});
```

The result includes baseline, up to three scenarios and three action comparisons. Scenario support/receipts are hypothetical. Baseline uses only confirmed ledger support and current accessible money; unreceived aid is excluded. Support is allocated first, restricted funds second, unrestricted funds last. Essential expenses precede nonessential expenses, then numerical priority and stable IDs determine allocation. Capped overlapping support cannot cover a cost twice. Amounts and unknowns are preserved as integer cents/null. Missing amounts yield incomplete projections and warnings.

Commitments accept explicit calendar dates/ranges or demo day offsets. Calendar dates should be used in persisted real records; day offsets are tied to the selected forecast start. Support amounts cap total coverage over its range; `consumed_cents` reduces that cap. Full category coverage may omit the cap. Model-produced quantity limits need conversion to a supported monetary or explicit full-coverage representation before calculation.

## Evidence and remaining work

From the repository root, run `npm ci` once and then `npm test` (Node.js 18+). Fifty tests cover the four required example outputs, update and data contracts, replay, expense reconciliation, support limits/overlap, restricted allocation, unknowns, record edits, balance refreshes, transfers, reversals, receipt links and clarification paths. Contract tests check Node/browser validator agreement, actual calendar dates, complete schedules, untouched inputs, missing-validator rejection and script order. Data tests check malformed/orphaned/duplicate records, typed audits, dated scenarios, unknown action costs and aggregate overflow. Manual-control/adapter tests check exact dollar parsing, version conflicts, receipts/aid separation, undo, reload, failed storage and retry identity. `npm test` rejects a stale generated validator. Regenerate with `npm run build:finance-contract` after schema/generator edits and commit both sources and output.

### Manual module requirement review

| Requirement | Evidence / boundary |
| --- | --- |
| Four exact 14-day examples; preserve an early gap despite later aid | Forecast acceptance tests retain Day 5/$55, Day 11/$25, and the specified final positions |
| Actual spending, receipt, transfer, balance refresh and correction | Typed updates, replay protection, explicit balance effects, two-sided transfer reconciliation, auditable undo |
| Unknown amounts, inaccessible/restricted funds, stale balances | Null/incomplete projections, restrictions/access tests, dates/expiry tests and rejected invalid data |
| Confirmed noncash support; overlapping coverage; hypothetical scenarios | Coverage before restricted funds/cash, capped support, immutable baseline, dated scenario tests |
| Feasible recovery-path costs | Dated cost inputs and unknown-cost warnings; P1 must supply already-feasible paths |
| Fixed interface and reproducible outputs | Ledger/update/forecast/result schemas, input-version propagation and output validation |
| Chat/dashboard shared state | Manual controls submit `finance.update` to the local mock; finance changes do not append to recovery/general transcripts |
| Durable case update and finance-triggered replanning | Pending P1 wrapper, authenticated command handling, concurrency, atomic durable commits and planner integration |

Support is normalized monetary/full-category coverage for the whole case; quantity or household-subset coverage must be converted to explicit eligible commitments/value before calling this module. No automatic quantity conversion, provider matching, or unsupported bank-import transition is claimed. Calendar schedules are required for real persisted use; relative day schedules remain demo inputs tied to the forecast start.

## Manual finance controls (C10 slice)

`frontend/finance-controls.js` supplies Update money, Add spending, Money received, editable planned costs, aid progress, source accessibility and audited undo. Entries have a preview and a separate Confirm & save action. The current balance can be left unchanged when a transaction is already reflected. Refresh confirmation explicitly describes the included transaction IDs. Blank planned/aid amounts remain unknown. A failed device save retains the original snapshot; retry uses the original event ID. Conflicts require a fresh review. Three conversation histories remain separate.

The mock calculates and saves the new ledger/forecast/version together; the planning date is explicitly fixed at October 10, 2026, matching the synthetic fixture. The real P1 service still rejects `finance.update`. Controls use an ordinary command envelope and a single case ledger so the adapter can be replaced later. C10 remains in progress for the rest of the descriptor-driven dashboard and browser interaction/accessibility verification. The automated browser blocked the local `file://` preview; no visual verification is claimed.

Timing detail: scenario receipts accept `date` or demo `day`, and optional `timing` (`before_expenses` default or `after_expenses`). A late receipt cannot erase that day’s earlier gap. Sources become usable on `available_on` and unused funds expire after `expires_on`. A balance snapshot dated before or after the forecast start makes the result incomplete until reconciled.
