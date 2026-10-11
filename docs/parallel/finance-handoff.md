# C08 remaining bounded finance domain handoff

October 11, 2026. Domain owner: finance. Durable integration owner: CaseService.

**Pure update/reconciliation, scenario/action-cost comparison and lifecycle
decision slices: READY_FOR_INTEGRATION. Full C08: IN_PROGRESS.** These are local
domain and contract proposals, not registered commands, accepted durable records,
agent tools, a finished dashboard, or live-provider proof. This handoff extends
the forecast-only handoff in `docs/finance-integration.md`; its original forecast
behavior and 59-check evidence remain intact.

## Scope and preserved evidence

Changes are confined to `backend/stillhere/finance/` (new `updates.py`,
`scenarios.py`, `lifecycle.py` and additive exports), new finance-specific tests,
`contracts/parallel/finance.schema.json` and this handoff. Existing
`forecast.py`, `tests/test_finance.py`, shared CaseService, commands, schema,
server, agent, README and progress files were not edited. Concurrent work was
preserved. No private configuration, credentials or secrets were opened or
loaded; no credentialed smoke or live-provider call was run.

Preserved SHA-256 signatures:

```text
forecast.py       42bf8a26da345dcf04e92afb251480d1f25f786d3e3b05c0e10db8d2d86d23ff
test_finance.py   20357042b0de815067623add9303a1f3346ac0b4d95c5a7dd0342239b0babd3c
```

## Public pure function signatures

Import from `backend.stillhere.finance`:

```python
apply_financial_update(
    ledger, update, *, event_id, effective_at, received_at, time_zone
)
forecast_finances(  # unchanged; additive receipts/support only
    ledger, *, start_date, time_zone, input_case_version, scenarios=None
)
validate_financial_scenario(
    ledger, scenario, *, start_date, time_zone, action_alternatives=None
)
set_financial_scenario(
    ledger, scenario, *, event_id, effective_at, received_at,
    time_zone, start_date, action_alternatives=None
)
compare_financial_scenarios(
    ledger, *, start_date, time_zone, input_case_version,
    scenarios=None, action_alternatives=None
)
invalidate_financial_outputs(prior_forecasts, *, target_case_version)
prepare_forecast_publication(
    forecasts, *, current_case_version, computed_at,
    publication_event_id, prior_forecasts=None
)
finance_reassessment(previous_forecasts, next_forecasts, *, changed_record_ids)
```

All functions are deterministic, framework-free and detached from their inputs.
There is no implicit clock, storage, provider, model, environment loader, service
configuration or network. Callers supply timestamps, IANA zone, case versions
and plain data. Calc/validation failures raise `FinanceInputError` with a field
path and fixed message; update/scenario-set failures return typed issues.
Messages do not echo rejected input values. Unknown money is `null`; actual
money is nonnegative integer USD cents. Python floats, bool amounts, negative
amounts and strings are rejected. Dates/UTC instants retain the original strict
forecast formats. Quantity support and source expiry/availability remain
explicit incomplete-forecast gates inherited from that engine.

### Update result and replay

Update/set returns `status: applied | needs_clarification | rejected`, `replayed`,
`next_ledger`, `changed_record_ids`, `reconciliation_notes`, and `issues`.
`applied` means **a validated proposal**, never a durable acceptance. Failures
return `next_ledger: null`, empty changes/notes and field-specific issues. Input
and audit state remain untouched, including a failure after the first transfer
endpoint or after reversing a correction in the tentative copy.

An accepted proposal appends a `finance_updates` journal entry: stable event ID,
SHA-256 logical fingerprint, original payload, effective/receipt times,
collection-qualified changed IDs, before/after records and reconciliation notes.
The fingerprint covers payload, normalized command effective instant and case
zone; object-key order and `Z`/`+00:00` on that command instant are equivalent.
Receipt time and transport case-version preconditions do not change identity.
Other payload changes, including array order, remain distinct logical inputs.

An identical accepted event returns `applied, replayed: true`, the supplied latest
ledger, empty current changes and `original_changed_record_ids`; it neither
reapplies money nor appends audits. Different logical input reusing the ID is
rejected. CaseService must retain its authoritative `(case_id, event_id)` replay
lookup, authorize before replay and resolve replay before version checks.
Domain replay is additional protection, not a replacement for that transaction.
Every collection and the inline journal are bounded to 256 records. Capacity
failure never drops history. Durable archival must retain replay fingerprints
outside a compacted snapshot before this bound becomes a production constraint.

### Financial operations

`update` is an object with `operation` and the listed fields. Unsupported
operation fields are rejected. Full records preserve caller-supplied provenance
and evidence; finance does not infer evidence or authorize a provenance claim.

| Operation | Payload fields and behavior |
| --- | --- |
| `set_money_source` | `record`: new cash/account/received-assistance source, explicit USD balance/accessibility/restrictions/as-of, optional aid link/reflected IDs. Credit/assets are rejected. Existing ID requires explicit correction/refresh. |
| `set_balance` | `money_source_id`, explicit nullable `balance_cents`, nullable `as_of`, explicit `reflected_event_ids`, optional `freshness`/`reason`. Replaces the snapshot without replaying any events; retains all previously acknowledged references. Earlier anchors need clarification. Internal `balance_epoch` records this snapshot event. |
| `record_expense` | `record` of kind `expense`; optional `balance_reflected_source_ids` and `commitment_fulfillment_reflected`. Applies source outflow once, fulfills only the explicitly matched occurrence. |
| `record_receipt` | `record` of kind `receipt`; optional reflected-source confirmation. Incoming restrictions must be explicit and must be preserved/narrowed by the target source. |
| `record_transfer` | `record` of kind `transfer`; optional reflected-source confirmation. Both endpoints reconcile atomically; transfer changes no commitment/aid fulfillment. Fees are separate matched expense events. |
| `set_commitment` | `record`: create/replace one-off or daily commitment. Nullable amounts and fulfillment stay unknown. Existing actual matches protect date/category/fulfillment from a separate destructive edit. |
| `set_aid` | `record`: create/replace entered stage, optional nullable amount/date, restrictions/evidence. Bounded stages: unknown/suggested/applied/pending/approved/denied/received. Received requires an actual posted receipt match. Tracker amounts are never added to money. |
| `set_support` | `record`: create/replace explicit support state, categories/commitment refs, dates, household coverage, limits/consumption and evidence. Confirmed support enters forecasts; hypothetical support never enters baseline. |
| `correct_record` | `collection`, full replacement `record` with same existing ID, and nonempty `reason`. Allowed collections: sources, commitments, aid, support. Source metadata/restrictions/accessibility/evidence can be explicitly corrected; reconciled amounts, anchors, epochs, currency/type and aid/event links require their specific accounting operation. |
| `reconcile_event` | `record_id`, same-ID `replacement`, `reason`, optional reflected-source/fulfillment confirmations. Explicitly changes a proposed import into its posted event while retaining pending/import/deposit refs. Also normalizes legacy posted records using explicit endpoint snapshot confirmations. |
| `correct_actual` | `record_id`, same-ID `replacement`, `reason`. Reverses the old arithmetic and fulfillment, then applies corrected amount/match once. Keeps posted kind/endpoints/effective time and newest source anchor; retains prior external refs and all before/after audits. |
| `reconcile_correction` | `record_id`, posted same-ID `replacement`, `reason`, complete `source_snapshots`, explicit `commitment_fulfillment` for every old/new matched occurrence. Corrects an event already absorbed by newer snapshots, using entered reconciled totals rather than guessing a second delta. Preserves kind/endpoints/aid link and every prior external reference. |

Actual-event inputs require `id`, `kind`, nullable `amount_cents`, `currency:
USD`, `source`, and `money_source_id`. `effective_at` defaults to the command
effective time; `date` defaults to its local date and must agree if supplied.
Expense requires `category`, optional `commitment_id` and `commitment_date`.
Receipt requires explicit `restrictions` when posted and optional `aid_id`.
Transfer requires a distinct `to_money_source_id`. `matching_refs` are bounded,
unique, caller-namespaced strings such as `synthetic_bank:transaction_001`.
`state` is `posted` or `proposed`; adapters normalize pending imports to
`proposed`, which the original forecaster already excludes.

### Matching, restrictions, snapshots and unknowns

No amount/text/provider similarity automatically matches records. A candidate
same-category/date commitment without an explicit match asks for clarification.
`commitment_id: additional` explicitly confirms extra spending; that sentinel
must not collide with a real commitment ID. If no candidate exists, unmatched
spending can be additional. Explicit commitment matches validate category and
dated occurrence; late settlement can reference a prior `commitment_date`.
Partial payment updates only that occurrence's fulfilled cents. Remaining
commitment is forecast as `max(0, amount - fulfilled)`; overpayment remains an
audited actual outflow, not an invented receipt or negative future expense.

Duplicate actual IDs require reconciliation/correction. A reused external
matching ref belonging to another actual event asks for clarification. Revisions
must retain every prior matching ref, so a pending ID cannot disappear during
posting. The backend/adapter must supply provider identity consistently; finance
cannot discover duplicate transactions with unrelated opaque IDs and no refs.

New arithmetic requires a known current balance/anchor. Outflow requires known
accessibility, compatible explicit restrictions and nonnegative resulting money.
Unknown restrictions/balance/fulfillment or stale/conflicting freshness return
clarification. Actual outflow conflicting with known fund availability/expiry
also needs reconciliation. Inaccessible/unknown balances and nullable commitments
can still be *recorded* explicitly; they remain incomplete/held in forecasting.
An unknown posted amount cannot change money; an explicitly proposed unknown
amount can remain a proposal. Zero is valid known money and never substituted
for an unknown value.

A transaction older than a later balance anchor must be explicitly acknowledged
as already included. `balance_reflected_source_ids` can acknowledge either/both
transfer endpoints independently; the other endpoint applies its delta once.
Every posted endpoint then names the actual ID in `reflected_event_ids`.
`commitment_fulfillment_reflected: true` separately confirms already-entered
fulfillment, validating it covers this event plus other known matched spending.
One balance snapshot does not imply its commitment is already fulfilled.
Legacy posted reconciliation requires all endpoint confirmations and explicit
fulfillment confirmation when the old record already named a commitment.

Arithmetic corrections retain per-source `balance_effects` and snapshot epochs.
A later refresh or an originally snapshot-reflected transaction prevents blindly
undoing its old delta. `reconcile_correction` supplies exactly one snapshot per
endpoint plus `{commitment_id, date, fulfilled_cents}` for all affected
occurrences. It protects other matched actual fulfillment, clarifies unknown
other spending, and links the corrected event without counting it again.
Changing posted transfer endpoints, dropping an aid link, or changing the kind
requires a separately reviewed explicit normalization; those edits are bounded
out of this implementation. No correction deletes the audit record.

Unreceived aid sources cannot fund expense/transfer operations or baseline money.
Receiving aid requires a dedicated `received_assistance` source with matching
`aid_id`, explicit matching receipt, and matching restrictions. The receipt
updates its source balance and aid's `actual_receipt_id`/stage together. It stores
the prior aid stage for correction; it never independently adds the aid award
amount. This bounded contract permits one matched receipt per aid item; split
awards require separate clearly identified items or a future installment model.

## Synthetic examples

Matched spending against known $300 cash and a $20 food commitment:

```python
proposal = apply_financial_update(
    ledger,
    {"operation": "record_expense", "record": {
        "id": "synthetic_spend_001", "kind": "expense", "amount_cents": 1200,
        "currency": "USD", "source": "user_reported", "money_source_id": "cash",
        "category": "food", "commitment_id": "food",
        "matching_refs": ["synthetic_bank:transaction_001"]}},
    event_id="synthetic_command_001", effective_at="2026-10-10T12:00:00Z",
    received_at="2026-10-10T12:01:00Z", time_zone="America/Chicago",
)
# proposed balance 28_800; matched fulfilled 1_200; remaining food cost 800.
# Retrying the same logical event never subtracts another 1_200.
```

A synthetic planner-independent alternative:

```python
alternative = {
    "id": "bus", "label": "Synthetic bus option",
    "replaces_commitment_ids": ["taxi"],
    "costs": [{"id": "bus_cost", "action_id": "bus_action", "category": "transport",
               "date": "2026-10-17", "amount_cents": 500, "essential": False}],
}
comparison = compare_financial_scenarios(
    ledger, start_date="2026-10-10", time_zone="America/Chicago", input_case_version=4,
    scenarios=[{"id": "bus_path", "label": "Bus assumption", "alternative_ids": ["bus"]}],
    action_alternatives=[alternative],
)
```

This example requires an unfulfilled nonessential action-linked `taxi` commitment.
The scenario removes only that explicitly named action cost, adds the dated bus
cost and preserves all essential expenses. There is no planner-agent dependency
or finance claim about whether a bus path is feasible. Use actual planner
snapshots later only after their owner validates feasibility independently.

## Scenario/action-cost boundary

`validate_financial_scenario` returns `scenario`, `comparison_ledger`,
`replaced_commitment_ids`, and `added_commitment_ids`. Baseline is reserved;
up to three independent scenarios can be stored/compared. The original
receipt/support validation still applies, including restrictions, unreceived aid
links, timing, support caps and unknowns. No scenario writes money or fulfillment.

Alternatives are `{id, label, costs: ExpenseCommitment[],
replaces_commitment_ids: string[]}`. Each cost requires a stable `action_id`,
explicit date/range and nullable cents. No alternative may claim actual
fulfillment. Each alternative supplies at least one dated cost: free is explicit
zero, and unknown is null; an empty cost list cannot erase a price. Cost IDs must
not collide with baseline or other selected costs.
Replacement requires explicit existing nonessential action commitments with no
fulfilled/unknown fulfillment, actual/proposed match or incoming support ref.
Essential expenses, including essential action expenses, cannot be deleted.
Overlapping replacement paths are rejected. Without replacement IDs, costs are
additions; finance never infers an exclusive path. Linked support must be
remapped in a reviewed future normalization, not dropped automatically.

`compare_financial_scenarios` calculates baseline from the original ledger, and
uses the **same unchanged `forecast_finances` engine** independently for each
prepared scenario. It exposes selected alternative IDs, exact dated action-cost
records and replaced IDs in `scenario_assumptions`. Unknown action costs make
only their scenario incomplete. No earlier receipt/expense timing is erased.

`set_financial_scenario` proposes scenario storage with the shared journal/replay
semantics. It replaces an existing scenario by ID without touching actual domains,
and retains an `action_cost_snapshot` plus `forecast_start_date`. Comparison
defaults to stored scenarios and their stored cost snapshots. Supplying different
costs for a saved scenario is rejected; explicit new `scenario.set` is required
to refresh the quote. The caller must assess quote freshness/plan revision and
ask for refreshed costs where needed; no age threshold is invented here.

## CaseService integration instructions

1. Review/freeze definitions from `contracts/parallel/finance.schema.json` into
   the shared boundary through its owner. They are **proposed `0.1` additions**,
   not permission to replace the existing shared schema. Schema validates shape;
   Python enforces valid calendar/IANA dates, cross-record refs, restriction
   compatibility, matching, caps, replay and unknown semantics. JSON Schema's
   integer definition accepts `1.0`; the pure runtime deliberately rejects all
   floats. Existing flexible evidence/provenance fields remain caller data.
2. For `finance.update`, authenticate/authorize the case/channel first, resolve
   durable replay, verify the expected case version and supply a detached ledger,
   case zone, backend-selected receipt time and stable effective time. Translate
   the transport payload into the typed operations above; the old section-5
   illustrative flat payload is not a new executable schema. Do not use a
   refreshed receipt timestamp as a changed logical effective time on a retry.
3. On domain `applied` with `replayed: false`, atomically commit its `next_ledger`,
   journal, case-version increment and existing whole-case audit exactly once.
   Translate domain replay into the existing `already_applied` command envelope.
   On clarification/rejection, commit no ledger, no forecast and no reassessment
   effect. Chat persistence is separately governed by the existing chat handler.
4. For `scenario.set`, follow the same authority/version/replay protocol and call
   `set_financial_scenario`. Store only its validated scenario assumptions/cost
   snapshot and audit. This can increment case version while actual money remains
   unchanged. Keep the hypothetical label in tools/UI; never post its receipt.
5. In the same accepted-update transaction, retain the last valid finance output
   but mark it `pending` using `invalidate_financial_outputs`, with
   `pending_input_case_version` naming the new target and `input_case_version`
   still naming the retained calculation. Relevant fact/planner/aid/support
   changes use the same invalidation rule. Schedule computation on the reconciled
   version; do not compute a forecast by adding tracker amounts to source balances.
6. Compute with `forecast_finances` or `compare_financial_scenarios` outside the
   storage lock. Use a forecast day compatible with balance anchors: an intraday
   snapshot cannot fund earlier day-1 expenses. Select a later start date or
   supply a normalized start-of-day snapshot; never strip the anchor to make an
   incomplete result look complete. Unknown and stale inputs retain their warnings.
7. Before durable publication, validate the entire output against the proposed
   forecast definition, then call `prepare_forecast_publication`. Recheck
   `input_case_version == current_case_version` **inside CaseService's atomic
   write**, plus active run/effect identity. Commit `computed_at` and stable
   `publication_event_id` only once. This helper is a decision, not a lock or
   full output-schema validator. `incomplete` is a valid calculation state;
   null first-gap/ending values must remain visible as unknown.
8. Stale input returns `conflict` and a retained prior result marked pending for
   the new version. On computation/schema/provider failure retain the prior
   valid result pending with an appropriate service issue, then reschedule from
   a fresh snapshot. Do not overwrite current inputs or publish the stale result.
   Publication should use the existing derived-effect protocol: avoid an endless
   self-invalidating version increment solely for publishing that same input.
9. After an accepted current calculation, call `finance_reassessment`. It
   requests clarification for incomplete baseline inputs; reassessment for new,
   worse, changed or resolved funding/essential gaps; and review when commitments
   or aid/support or available opening money changed. Its request carries the calculation version and
   changed refs with `preserve_completed_actions: true`. CaseService schedules
   and deduplicates the versioned planner effect, preserving completed work and
   checking newer inputs before accepting a plan. The helper never edits a plan,
   selects a feasible action, submits aid, contacts anyone, or dispatches help.

For agent adapters, authenticated case/session/run context and authorization
remain backend-injected. Stable child event IDs derive from the parent turn and
logical finance intent. Schema-bound tools call these functions through
CaseService; no tool writes directly to storage. `read_financial_summary` must
show current money separately from forecasts, held restrictions/unknowns,
unreceived aid and conditional scenarios. Calculation/model outputs never grant
consent or access. Chat/control parity and durable replay need integration tests
before registration.

## Deterministic verification

```sh
.venv/bin/python -W error::ResourceWarning -m unittest \
  tests.test_finance tests.test_finance_updates \
  tests.test_finance_scenarios tests.test_finance_schema
```

**170 focused checks pass**: the unchanged 59 original forecasts, 65
update/reconciliation checks, 36 scenario/lifecycle checks and ten proposed-schema
checks. They cover all four canonical forecasts independently and via comparison,
source/commitment/import identity, lost-response replay, pending/posting,
one-/two-sided snapshot reflection, atomic transfers, corrections before/after
refresh and later spending, matching-reference retention, aid receipt/correction,
restrictions/accessibility/expiry, unknown-versus-zero, daily occurrences,
determinism, mutation/alias isolation, invalid values/refs/bounds, scenario quote
refresh, essential preservation, stale publication and reassessment.

| Canonical input, start October 10 | First gap | Ending cents |
| --- | --- | --- |
| $300, $65/day, $30 day-1 action cost | October 14, day 5, $55 | -64,000 |
| Food/lodging support days 1–7 | October 20, day 11, $25 | -22,000 |
| Same support, hypothetical $500 day 8 | None through day 14 | 28,000 |
| Same support, hypothetical $500 day 12 | October 20, day 11, $25 | 28,000 |

A credential-free workspace discovery found 610 tests and selected 605 non-HTTP
checks: **603 passed; two shared tests errored**:
`test_case_service.CaseServiceTests.test_correction_retains_completed_work_and_marks_old_results_pending`
and `test_intake.IntakeTests.test_partial_updates_preserve_prior_facts_needs_and_completed_work`.
Both dereferenced a null returned case snapshot, outside finance-owned files.
This is workspace-snapshot evidence during concurrent changes, not a claimed
clean full-suite result or diagnosis of their underlying cause. Shared owners
must resolve/reverify it. Five HTTP checks were excluded under the existing
documented host loopback limitation; no HTTP or live smoke result is claimed.
Synthetic configuration-loader checks use temporary noncredential filenames;
no private configuration is loaded by this regression command.

## Remaining gates

- Shared owner review/freezing and mapping of ledger/schema/command envelopes,
  category IDs, entered provenance, aid stages and cost-snapshot revision context.
- Durable CaseService transactions, restart/replay/version races, derived forecast
  publication/invalidation and deduplicated finance-triggered planner effects.
- Agent adapter schemas/access checks, chat/control parity and user-run live
  provider smoke. Pure calculation proof does not verify a registered agent tool.
- C05 owner-reviewed feasible action-cost snapshots and refresh rules. Synthetic
  costs prove the boundary without depending on the planner agent.
- Dashboard/backend integration and household acceptance, including unknowns,
  restrictions, conditional labels, actual versus projected money and completed
  action preservation. Full C08 remains separate from these pure slice results.
- Bounded future normalization: installments, posted endpoint/kind changes,
  support quantities and availability/expiry allocation, provider-specific bank
  adapters, explicit support remapping on path replacement and durable archival.
  None is inferred, silently normalized, or advertised as implemented here.
