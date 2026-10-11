# C08 deterministic finance forecast handoff

Date: October 11, 2026. Owner: P2 finance; P1 owns shared contracts and backend
assembly. Scope: the pure forecast slice under `backend/stillhere/finance/`.

**Forecast slice: READY_FOR_INTEGRATION. Full C08: IN_PROGRESS.** This is a
14-day calculation boundary, with one baseline and up to three additive
hypothetical scenarios. Financial updates, reconciliation, durable forecast
publication, agent adapters, action-path replacement/comparison and frontend
integration remain later slices. Live-provider verification is not applicable
to this dependency-free calculation; no new provider/model proof is claimed.

Only `backend/stillhere/finance/`, `tests/test_finance.py` and this handoff were
edited for C08. The browser engine and fixture, C09, C05 planner, CaseService,
agent tools and shared schema/progress documents belong to their owners.
Concurrent edits to those files were preserved. No credential file was read,
no environment file was loaded, and no credential-dependent smoke was run.
This slice makes no model/configuration change; Sonnet 4.5 remains the selected
model. The user's successful C04 USAGov/Sonnet proof remains separate evidence.

## API and proposed local contract

```python
from backend.stillhere.finance import FinanceInputError, forecast_finances

result = forecast_finances(
    ledger,
    start_date="2026-10-10",
    time_zone="America/Chicago",
    input_case_version=4,
    scenarios=[],
)
```

`result` is ordinary JSON-shaped data with `contract_version: "0.1"`,
`input_case_version`, `baseline` and `scenarios`. Each forecast repeats the
contract/version, scenario ID/label, time zone, inclusive start/end dates,
state, opening money, daily projections, first gaps, ending position,
assumptions, conditional scenario assumptions and typed warnings. Scenario
results are ordered by ID. There is no implicit clock or `computed_at`; the
eventual CaseService wrapper supplies calculation/receipt time separately.

These field names are **proposed local definitions**, not a frozen shared
schema. P1/P2 must review them before an adapter exposes them as shared `0.1`
records. `FinanceInputError` is a `ValueError` with a field path and fixed
message; it does not echo financial values. Validation failures apply no
changes. The caller owns authorization and any command/result translation.

All monetary values are nonnegative integer USD cents on input; unknown is
explicit `null`. Floats (even `2.0`), booleans, strings and negative amounts
are rejected. Negative output positions are projected gaps. Dates are exact
`YYYY-MM-DD`; instants are RFC 3339 UTC (`Z` or `+00:00`), with seconds and
optional microseconds. The explicit case IANA zone determines calendar dates,
including daylight-saving changes. Case version is a positive integer.
Each input collection is bounded to 256 records; identities must be unique
within it. A scenario may add up to 256 receipts and 256 support records.

### Ledger boundary

The ledger requires `money_sources` and `expense_commitments` arrays.
`actual_events`, `aid` and `support` default to empty arrays when omitted.
Arrays mean the records in the caller's supplied scope, not proof that the
household has no other needs. Existing provenance metadata remains in the
input; this calculator neither establishes evidence nor updates it.

| Record | Fields used by this slice |
| --- | --- |
| Money source | `id`; `type`: `cash`, `account`, `received_assistance`; `currency: "USD"`; explicit `balance_cents`, `accessible` and `as_of` (each may be null); explicit `restrictions`; optional `reflected_event_ids`, `aid_id`, `freshness` |
| Expense | `id`, `category`, explicit `amount_cents` (nullable), `essential` boolean; `priority` defaults to 100 (lower first); either `date` or inclusive daily `start_date`/`end_date`; optional `action_id` |
| One-off fulfillment/timing | `fulfilled_cents` defaults to 0, may be null; optional UTC `due_at` must match `date` in the case zone |
| Daily fulfillment | `fulfilled_cents_by_date`: date-to-integer/null map, default empty; each key lies in the recurrence range. Unspecified occurrences have zero fulfillment. Daily `fulfilled_cents`/`due_at` are rejected as ambiguous. |
| Aid | `id`, `stage`; `received` requires a linked reconciled money source. Every other stage stays outside baseline money. Tracker amounts are never independently added. |
| Actual event | `id`; proposed records (`state: "proposed"`) do not affect baseline. Every other record must already be named in money-source `reflected_event_ids`. |
| Support | `id`, `state`: `confirmed`, `hypothetical`, `unknown`, `unavailable`; inclusive `start_date`/`end_date`; nonempty `categories` and/or `commitment_ids`; `household_coverage`: `full`, `partial`, `unknown`; optional monetary limits/full-cost declaration/consumption |

`restrictions: []` explicitly means unrestricted. A nonempty list contains
compatible expense category IDs; `null` means unknown restrictions, so funds
are held separately and never allocated. Source availability/expiry constraints
(`available_at`/`expires_at`) produce an incomplete warning and exclude that
source until normalized; this slice does not silently ignore such constraints.
Credit limits and assets are rejected as money-source types.

A balance must be anchored **at or before local midnight on forecast day 1**.
A later/intraday snapshot cannot fund earlier day-1 costs and produces an
incomplete result. For an intraday refresh, reconcile spending and either
prepare a start-of-day anchor or select a later forecast start date. Older
anchors retain their timestamp and emit `balance_before_start`; the caller
must have reconciled intervening events. Explicit `freshness: "stale"`,
`"conflicting"`, `"unknown"` or null makes the result incomplete. There is no
invented freshness threshold or hidden current-time check.

This slice consumes **already reconciled balances and fulfillment**. It does
not infer matches or replay actual events. Unreflected actual events produce
`unreconciled_actual_event`, keep known-value subtotals, and prevent an
authoritative forecast. A received aid record without a source linked by
`aid_id` also produces an incomplete result. Reflected receipt/expense/transfer
records are not counted again. Partial actual spending reduces only the
matched commitment occurrence via normalized fulfillment. The later update
slice must establish those links, including balance refreshes, both sides of
transfers, pending/posted/import matches, fees, corrections and replay IDs.

### Support and allocation

Support requires explicit `covers_full_cost: true` or a known
`daily_limit_cents` and/or `total_limit_cents`. If both limits exist, both apply.
An explicit null limit is unknown, not unlimited. `consumed_cents` defaults to
0 and reduces the total limit once across the whole horizon. Consumption
without a total limit requires later normalization and is not applied.
Partial household coverage requires a known monetary limit; unknown coverage
cannot remove a full household expense. Quantity limits require an upstream
value/expense conversion and produce `unknown_support_coverage` here.

If both category and commitment filters are supplied, both must match;
commitment IDs must reference supplied expense records. Daily
caps are shared across matching expenses on that date; total caps span all
dates. Overlapping support only covers the remaining amount, so savings never
exceed the expense. Confirmed support enters baseline; suggested/hypothetical,
unknown and unavailable support do not.

Allocation order is deterministic:

1. Preserve known expense/receipt UTC times. Date-only receipts start the local
   day; date-only expenses follow that day's receipts/timed items. Receipts win
   exact time ties. Thus a known late receipt cannot fund a known earlier cost.
2. Within the same expense time, essential expenses precede others, then lower
   priority numbers, then expense IDs. Chronology takes precedence over priority.
3. Apply eligible confirmed support, then scenario support, each by stable ID.
4. Apply compatible restricted balances by narrower category-set size, then
   stable source ID; then unrestricted money.

This is an entered-order allocator, not a global benefits/cost optimizer. A
positive total ending position can coexist with a gap when remaining funds
cannot pay that expense category. Unrestricted projected deficits accumulate
for the cash-flow comparison; later receipts can improve the position but
cannot erase earlier unmet-need records. Restricted pools never go negative.

### Scenarios

A scenario is `{id, label, receipts: [], support: []}`. `baseline` is reserved;
there are at most three scenarios. Scenarios are independent additions to the
baseline; they never replace confirmed support or delete essential costs.
Unsupported scenario fields, including alternative action replacement, are
rejected until that boundary is agreed.

Each receipt has `id`, `state: "hypothetical"`, explicit `amount_cents`
(nullable), `currency: "USD"`, explicit `restrictions`, `date`, optional UTC
`available_at`, and optional `aid_id` referencing an existing unreceived aid
item. Duplicate aid receipts within one scenario and a receipt for already
received aid are rejected. Receipt IDs cannot duplicate opening source IDs.
An out-of-horizon receipt is excluded with a notice and remains visible in
`scenario_assumptions`. Scenario support uses the support shape above but must
have `state: "hypothetical"` and its own identity. Baseline is unaffected by
scenario unknowns. These assumptions do not establish approval, receipt,
probability, or support availability.

### Incomplete results and output interpretation

Warnings have `code`, `record_id`, fixed `message` and
`affects_completeness`. Any completeness-affecting warning sets
`state: "incomplete"` and adds `incomplete_forecast`. Definitive
`first_gap`, `first_essential_gap`, daily/per-expense `unmet_cents`, daily
`projected_position_cents` and `ending_projected_position_cents` are then null.
**A null first gap in an incomplete result does not mean no gap.**

Unknown opening money stays null in `opening_accessible_cents`; the known
subtotal remains in `opening_known_accessible_cents`. Null expense amounts
and fulfillment are preserved in the daily expense details. A row containing
unknown costs has null `expenses_due_cents`/`uncovered_expense_cents` plus
separately labeled known subtotals. Unknown receipts similarly retain null
`receipts_cents` with a known subtotal. Held unknown-restriction funds are
excluded from allocation and known spendable subtotals.

`known_inputs_*` fields and `ending_known_inputs_position_cents` expose only
the provisional calculation of entered known values. They are not bounds,
actual cash balances, or coverage guarantees: unknown costs/support/balances
could alter allocations and the date of the first gap. For conservative
presentation, all authoritative projection rows are null when the result is
incomplete, including dates preceding a later unknown cost.

`first_gap` is the first day with any entered unmet expense; its amount sums
that day's unmet costs and its IDs name those costs. `first_essential_gap`
separately identifies the first essential-only gap. Daily rows include receipts,
due/support/restricted/unrestricted expense amounts, remaining restricted
money, projected positions, expense/action IDs and allocation details. The
total projected position includes remaining restricted money, while
`known_inputs_unrestricted_position_cents` exposes the separate unrestricted
projection. Consumers must show restrictions and gaps with the total.

## Validation evidence

Focused command (standard library; no service/configuration required):

```sh
.venv/bin/python -W error::ResourceWarning -m unittest tests.test_finance -v
```

**59 focused checks pass**, on Python 3.14.7. They verify all four canonical
examples independently and together as baseline plus three scenarios:

| Synthetic input, start October 10 | First gap | Ending projected position |
| --- | --- | --- |
| $300, $65/day, $30 day-1 cost | October 14, day 5, $55 | -$640 |
| Food/lodging coverage on days 1–7 | October 20, day 11, $25 | -$220 |
| Same coverage, hypothetical $500 receipt day 8 | None through day 14 | $280 |
| Same coverage, hypothetical receipt day 12 | October 20, day 11, $25 | $280 |

Additional checks cover restricted rent/food allocation, overlapping support,
shared caps/consumption, partial household coverage, essential/user priority,
unreceived aid, normalized reflected receipts/spending/transfers, per-date
fulfillment, same-day/early/late receipts, local UTC date boundaries and DST,
unknown amounts/restrictions/accessibility/anchors, stale/conflicting inputs,
out-of-horizon receipts, record bounds, invalid dates/cents/references,
JSON output, case versions, repeat/permutation determinism and input/output
alias isolation. Failed validation also preserves the input ledger.

The final credential-free regression run discovered **297 checks and passed
all 292 selected non-HTTP checks**, including concurrent C05 and pinned SDK
checks. No selected check was skipped. This is a final workspace-snapshot
count, not an edited shared tracker total. Reproduce that selection with:

```sh
.venv/bin/python -W error::ResourceWarning - <<'PY'
import unittest

def leaves(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from leaves(item)
        else:
            yield item

selected = [test for test in leaves(unittest.defaultTestLoader.discover('tests'))
            if not test.id().startswith('test_http.')]
result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
raise SystemExit(not result.wasSuccessful())
PY
```

An earlier workspace run encountered nine concurrent C05 test setup errors
(`KeyError: case_id`); a temporary C05-excluding selection passed 262 checks.
C05 was left to its owner, and the final C05-inclusive rerun passes. Five
existing HTTP checks were excluded under the documented host loopback
limitation, not claimed as verified here. No HTTP or live-provider smoke was
attempted for this calculation slice.

Usage was checked at start and between implementation/validation milestones;
remaining usage stayed above 20%. No credential settings or model selection
were changed by the finance work.

## Proposed shared-contract/tracker updates and next slices

The following are handoff proposals; shared files have not been edited:

1. **P1/P2 shared boundary review:** add/freeze finance source, commitment,
   support, scenario receipt, forecast, daily allocation and warning definitions
   in the shared schema, including null/partial semantics, source/aid links,
   reflected event IDs and per-date fulfillment. Confirm category IDs, essential
   priority, anchor/timing semantics and `first_gap` versus `first_essential_gap`.
   Retain `0.1` only if these additions fit the existing compatibility protocol.
2. **Tracker proposal:** retain full `C08 Finance: IN_PROGRESS`; record the
   `forecast_finances` slice as `READY_FOR_INTEGRATION` with the package path,
   59 focused checks and canonical/restricted/unknown/timing/immutability
   evidence. Record integration/provider gates separately and link this handoff.
   Do not promote C08 or the household journey to complete from this evidence.
3. **Reconciliation/update slice:** implement pure `apply_financial_update`,
   auditable proposed updates, commitment/receipt/import matches, balance refresh,
   transfer accounting, pending/posted changes, corrections and replay. Only
   CaseService commits a validated next ledger atomically under existing
   authorization, event IDs and case-version checks.
4. **C05/C08 cost boundary:** planner supplies feasible paths, dated nullable
   costs and action IDs as ordinary data. Selected costs can already appear as
   commitments with `action_id`; unknown amounts remain incomplete. Agree a
   separate alternative-selection/replacement contract before comparing paths;
   this slice does not choose feasibility or silently replace/drop essentials.
5. **CaseService/agent integration:** authorize reads, supply a reconciled
   snapshot/version, recheck input version before publishing a result, preserve
   pending/stale prior results on concurrent changes, and attach server
   calculation time. Add scoped schema-validated forecast tools only after this
   boundary is frozen. CaseService owns every durable ledger/result write.
6. **P2 fixtures/UI and acceptance:** adapt prototype relative day numbers and
   date-only `as_of` to explicit dates/UTC anchors without editing the existing
   browser engine in this slice. Render unknowns, provisional subtotals,
   restricted balances, first essential gaps and conditional scenarios. Verify
   chat/control parity and financial updates through C01 in later integration.

Remaining limitations include quantity support normalization, fund expiry or
delayed accessibility, uncertain actual-event matching, ongoing imports,
alternative action replacement, scoped UI/tools, finance-triggered replanning
and durable integration. Caller-supplied confirmed/support facts and reconciled
balances remain prerequisites; this calculator is not an evidence verifier or
complete financial-event service.
