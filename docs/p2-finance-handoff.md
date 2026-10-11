# P2 finance handoff

Status: draft integration contract. C08 remains in progress; these operations have module-level evidence, not backend integration evidence.

## Entry points

`frontend/finance-engine.js` has no database, model or network dependency. In Node:

```js
const { apply_financial_update, forecast_finances } = require('./frontend/finance-engine.js');
```

The browser receives the same functions through `window.StillHereFinance`. Inputs are not mutated. Persist only the proposed `result.ledger` of an `applied` result. Other statuses are `already_applied`, `needs_clarification`, and `rejected`. Financial record edits preserve their prior record in `ledger.record_updates`; transactions and reversals remain in `ledger.actual_events`.

The proposed update input schema is `contracts/finance-update.schema.json` (JSON Schema 2020-12). AJV 8.20.0 compiles it into the checked-in `frontend/finance-validation.js`, which the engine uses in both Node and the browser before domain checks. Required fields, unknown fields, types, safe integer cents, calendar dates, unique lists, and exactly one complete commitment/support schedule are enforced. No third-party runtime package or network request is needed. Load the local validator before the engine in a browser; missing validation prevents updates. Its structural rules complement the module's reference, balance, date-ordering and reconciliation rules. This is an update-input schema, not a complete persisted-ledger or forecast schema, and it has not been merged into P1's case command schema. P1's current validator is deliberately limited and must not silently accept unsupported schema keywords.

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

From the repository root, run `npm ci` once and then `npm test` (Node.js 18+). Thirty-five tests cover the four required example outputs, replay, expense reconciliation, support limits/overlap, restricted allocation, unknowns, record edits, balance refreshes, transfers, reversals, receipt-link preservation and clarification paths. The contract tests compare the generated Node/browser validators with AJV for all 11 operations and malformed inputs; they also check calendar dates, schedule structure, unchanged inputs, runtime agreement, missing-validator rejection, and script order. `npm test` rejects a stale generated validator. After schema/generator edits, run `npm run build:finance-contract`, then commit both the source and generated file.

Source access edits, conditional record undo, calendar dates, availability/expiry, stale opening balances, and before/after-expense receipt timing now have regression evidence. Remaining P2 C08 work includes persisted-ledger and forecast/scenario input/output schemas and a final requirement audit. Update-input validation is enforced; the entire stored ledger and forecast input are not yet schema validated. P1 still owns authenticated transport, durable commits, concurrency, and integration with recovery replanning. Optional bank-import transitions are deferred with Plaid; they are not represented as working behavior.

Timing detail: scenario receipts accept `date` or demo `day`, and optional `timing` (`before_expenses` default or `after_expenses`). A late receipt cannot erase that day’s earlier gap. Sources become usable on `available_on` and unused funds expire after `expires_on`. A balance snapshot dated before or after the forecast start makes the result incomplete until reconciled.
