# C05 remaining bounded planner domain handoff

October 11, 2026. Scope: `backend/stillhere/planner/`, planner-specific regressions,
and this handoff; proposed additions are in `contracts/parallel/planner.schema.json`.
CaseService owns every durable write. These functions perform no database,
network, model, environment/configuration, or finance-module operations.

**Remaining bounded domain slices: READY_FOR_INTEGRATION. Full C05: IN_PROGRESS.**
The existing three slices remain intact. The latest milestone, rather than stale
opening paragraphs in the older handoffs, records passing read-only planner and
live saved-plan/task/replay proofs, including two `mode: plan` successes at 12.444
and 13.516 seconds. That evidence is retained; the new slices have synthetic
verification only. Shared assembly, trusted confirmation ingestion, P1/P2 schema
review, finance consumption, UI/tool exposure and new live workflow verification
remain gates. No full-component, deployment, household eligibility, agency outcome
or Colorado live-extraction verification is claimed.

## Implemented slices and boundaries

| Slice | Implemented behavior | Evidence / remaining gate |
| --- | --- | --- |
| Typed evidence/action links | Exact consumer action/rule/version/node and typed target IDs. Evidence keys must match the published predicate; action links also pin the target rule/version. No matching from titles/descriptions. Missing or mismatched targets remain explicit unknowns. AND/OR frontiers suppress unnecessary optional blockers. | Synthetic regression passes; authorized evidence/link records and shared schema assembly pending. |
| Source-supported confirmation consumption | Exact case/action/rule/version/node; explicit Boolean value, observation/expiry and supporting reviewed source IDs. Household claims, wrong sources/scopes, stale/conflicting/future/expired records and stale/future/expired reviewed sources remain unknown. A supported false predicate blocks only its modeled gate. | Pure consumption passes; a trusted ingestion/authorization path is still required. This function does not obtain agency confirmation. |
| Cross-action planning and ordering | SCC cycle diagnostics name actions and links. Cyclic leaves are unmet, producing required blockers. Optional cyclic OR branches retain diagnostics without blocking a satisfied independent branch. Prerequisites precede dependents, then lower user priority, earlier deadline and stable ID decide ties. | Synthetic self/two-action cycles, OR suppression and ordering pass; link persistence and reviewed alternative resolution pending. |
| Auditable completion correction | Correct the latest explicit retained completion report by event ID. Preserve original history, append a correction with occurrence/receipt times and reason, mark the route and active transitive consumers stale, and mark the proposed plan pending. Preserve other completed/skipped work. | Pure correction passes; CaseService command/replay/audit/version integration pending. No financial reversal occurs. |
| Dated nullable action costs | Explicit USD cents, dates, optional UTC due time, essential flag, observation/state and attribution. Unknown amount/date remains null. Stale/unverified amounts export as null while original reported values remain visible. Explicit zero stays zero. | Synthetic costs/provenance/local-date/timing checks pass; shared summary and finance adapters pending. |
| Finance export and selection proposal | Plain path/cost/commitment data; explicit hypothetical selection of current provisional/ready paths. Replace only untouched explicitly planner-owned costs for selected same-rule/version alternatives. Preserve essentials, historical/fulfilled/actual-linked costs and unrelated commitments. Clarification suppresses the whole executable patch. | Independent synthetic finance records pass; no import from `backend/stillhere/finance/`. C08 boundary review and reconciliation remain required. |

All new functions return detached JSON-shaped data. They preserve caller inputs
on both successful and failed validation. `InvalidInput` reports a field and a
fixed validation message without echoing private input values. Bounds: 32 retained
actions, 128 total links/evidence/confirmation records each, 32 links and 32 graph
nodes per action, eight graph levels, 16 cost items per action, and 256 existing
finance commitments. History stays bounded at 64; correction rejects capacity
rather than silently discarding the report it must reference. Earlier audit
records must remain available through CaseService.

`input_case_version` is a caller-supplied snapshot version, not write authority.
Dependency evaluation rejects action inputs from a later version. All eligibility
remains `unknown`; resolution produces `provisional`/`pending` plans and never
upgrades the partial catalog to confirmed eligibility or a fully feasible route.
Existing household access constraints and inability/partial-policy questions are
retained. A task completion is a household report, never agency acceptance.

## Public pure function signatures

Exported from `backend.stillhere.planner`:

```python
evaluate_options(snapshot, rules)  # existing, unchanged

resolve_dependencies(
    plan, *, case_id, input_case_version, links, evidence, confirmations, as_of
) -> dict  # proposed plan; does not increment plan/case versions

order_actions(plan, *, priorities=None, deadlines=None) -> dict

correct_completion(
    plan, payload, *, occurred_at, received_at, event_id, input_case_version
) -> dict  # proposed plan version +1; pending input case version +1

set_action_costs(plan, updates, *, as_of) -> dict

export_action_costs(
    plan, *, input_case_version, as_of, time_zone
) -> dict

propose_alternative_selection(
    cost_export, selected_action_ids, *, existing_commitments
) -> dict
```

Except for the explicit correction proposal, pure transformations retain the
plan version. The eventual CaseService transaction supplies the committed plan
revision, case version and audit event. No function issues commands or mutates
facts, evidence, applications, sources, money, consent or public knowledge.

`order_actions` consumes resolved dependency links. Explicit priorities are
integers 0–1000 (lower first; default 100). Deadlines are exact calendar dates
or null. Dependencies take precedence over priority/deadline; terminal records
retain their original relative order after active planner actions. Unrelated
records retain relative order. Changing historical terminal priority/deadline
metadata is rejected. A cyclic residual order is deterministic display order,
not an executable sequence: consult the explicit cycle blockers first. Dates
alone do not establish an official deadline; the caller must preserve the origin
of an entered/reviewed deadline in its durable event.

## Typed records and examples

The standalone proposal is executable by the planner's strict local validator,
not registered with the shared CaseService validator. It contains proposed
`PlannerDependencyLink`, `PlannerEvidence`, `PlannerConfirmation`,
`PlannerRequirementEvaluation`, `PlannerAction`, `PlannerPlan`, `PlannerCycle`,
`PlannerTaskHistory`, `PlannerCompletionCorrection`, `PlannerPriority`,
`PlannerDeadline`, `PlannerCostItem`, `PlannerCostUpdate`, `PlannerCostCommitment`,
`PlannerCostPath`, `PlannerCostExport` and `PlannerSelectionProposal` definitions.
Shared supporting definitions are copied for a self-contained review artifact;
this is not a second persistence layer or a frozen replacement schema.

An action dependency explicitly binds two versioned records:

```json
{
  "id": "link_replace_after_proof",
  "action_id": "action_replace",
  "rule_id": "replacement_rule", "rule_version": "2026-10-10.1",
  "node_id": "proof_obtained", "kind": "action",
  "target_id": "action_obtain_proof",
  "target_rule_id": "proof_rule", "target_rule_version": "2026-10-10.1"
}
```

Use `kind: "evidence"` for a published evidence predicate or
`kind: "confirmation"` for an `authority_confirmation` predicate. These links
have null `target_rule_id`/`target_rule_version`. The consumer pin remains
mandatory. A single leaf has one link; multiple accepted options use published
OR leaves rather than ambiguous multiple matches.

```json
{
  "id": "evidence_birth_certificate", "case_id": "synthetic_case",
  "key": "certified_us_birth_certificate", "available": true,
  "state": "user_reported", "observed_at": "2026-10-11T06:00:00Z",
  "expires_at": null, "source_ids": []
}
```

This establishes only the reported availability of that explicitly linked proof.
It does not establish that an agency accepted it. All requirements retain their
published `timing` and `evidence_state`; no document contents, document uploads,
OCR or identity numbers are needed. Late-stage evidence remains labeled with its
published timing; this slice does not implement C06 submission-stage transitions.

A confirmation record is separate from a household assertion:

```json
{
  "id": "confirmation_checklist", "case_id": "synthetic_case",
  "action_id": "action_replace", "rule_id": "replacement_rule",
  "rule_version": "2026-10-10.1", "node_id": "checklist_confirmed",
  "value": true, "state": "source_supported",
  "observed_at": "2026-10-11T06:00:00Z", "expires_at": "2026-10-18T06:00:00Z",
  "source_ids": ["reviewed_agency_source"]
}
```

This is an input shape, not evidence that any real agency made that confirmation.
CaseService must establish household-specific applicability and trusted origin
before supplying such a record. Merely attaching an official public page to a
household claim cannot establish an individualized agency decision. The resolver
requires the cited source to be in the exact requirement and action attribution,
reviewed/current, retrieved/reviewed/updated by `as_of`, and not expired. Conflicting
records are supplied as `state: "conflicting"`; do not pick a favorable claim.

A completed target satisfies an action link only with the latest explicit
completion report and occurrence/receipt times at or before the query. Its pinned
historical rule version may satisfy that exact historical dependency even when
the action's fact evaluation is stale. A changed target version is unknown, not
a substitution. Skipped/uncompleted targets do not satisfy positive completion
predicates. No readiness status, title or assistant prose completes a task.

A correction payload is disjoint from ordinary completion/skipping/inability:

```json
{
  "action_id": "action_obtain_proof",
  "completion_event_id": "event_report_done",
  "reason_code": "reported_in_error"
}
```

Reasons are `reported_in_error`, `not_completed`, `wrong_action`. Only the latest
retained completion report may be referenced. Future/out-of-order corrections,
missing references and reused event IDs are rejected. CaseService resolves exact
replay before invoking the function. The appended history retains
`correction_of`, `correction_reason`, `occurred_at`, `received_at` and
`provenance: "user_reported"`. Correction makes the action blocked if its existing
blockers remain, otherwise waiting; it never declares readiness. Reassess affected
programs before clearing stale markers. Completed/skipped consumers remain
historical reports. Finance must handle any real spending correction separately.

## Cost/finance boundary

```json
{
  "action_id": "action_replace", "rule_id": "replacement_rule",
  "rule_version": "2026-10-10.1",
  "items": [{
    "id": "replacement_fee", "category": "documents", "essential": false,
    "amount_cents": null, "date": "2026-10-12", "due_at": null,
    "state": "unknown", "observed_at": null, "source_ids": []
  }]
}
```

Use explicit nonnegative integer cents; floats, booleans, strings, negatives and
nonfinite values are rejected. Empty cost lists cannot establish zero cost.
Known zero requires an explicit zero-valued record with date and provenance.
A known amount with an unknown date keeps the date null; no deadline or implicit
clock fills it. UTC instants require seconds and `Z`/`+00:00`; dates are exact
`YYYY-MM-DD`. A known `due_at` must fall on `date` in the supplied case IANA zone.
Source-supported costs require matching current reviewed attribution. A household
report is usable as a labeled entered cost, not a verified public fee.

`cost_items` is the proposed detailed cost field. Legacy `costs` remains unchanged
for compatibility with existing tools; its unknown summary is not authoritative
for new costs. New UI/summary adapters must consume/export `cost_items` after
schema review. The resolver retains existing legacy cost questions until that
assembly replaces them with export warnings. Historical completed/skipped costs
cannot be overwritten by `set_action_costs`; expense corrections belong to C08.

The cost export has `contract_version`, `input_case_version`, `plan_version`,
`as_of`, `time_zone`, `currency: "USD"`, and one `paths` entry per owned action.
Each entry includes exact rule/version, action status/freshness, same-version
alternative IDs, `selectable`, `cost_state`, original `cost_items`, normalized
`commitments`, and warnings. No path is selected automatically. Provisional
current waiting paths may be selected for **hypothetical comparison**, retaining
`provisional_action`; blocked, stale, removed, completed and skipped paths are
not selectable. Terminal entries expose historical costs but have no future
commitments. Legacy unknown fee/transport costs export two explicit null records.

A commitment has a stable hash ID from action/cost IDs, `action_id`,
`planner_cost_id`, category, nullable date/cents, optional UTC `due_at`, explicit
essential flag/priority and source IDs. Unknown dates or past expense times require clarification/reassessment
before adapting to C08's dated input; do not omit an unknown expense. Unknown
amounts remain nullable and must make a forecast incomplete.

Selection example, using entirely synthetic existing finance data:

```python
exported = export_action_costs(
    costed_plan, input_case_version=7,
    as_of="2026-10-11T06:00:00Z", time_zone="America/Chicago",
)
proposal = propose_alternative_selection(
    exported, ["action_online"], existing_commitments=[
        {"id": "essential_food", "essential": True,
         "category": "food", "date": "2026-10-12", "amount_cents": 2000},
        # A previous exported planner commitment, plus normalized finance metadata:
        {**previous_office_commitment, "origin": "recovery_planner",
         "fulfilled_cents": 0, "actual_event_ids": []},
    ],
)
```

The result carries the same input/plan versions, `hypothetical: true`, selected
IDs, retained IDs, removal IDs, added commitments and typed issue codes. It
proposes no receipts, approval, support availability, probability or savings.
A `proposed` result may retain `eligibility_and_policy_provisional`; that is
explicitly a hypothetical comparison warning. Other issues yield
`needs_clarification` and empty add/remove arrays; no partial patch is executable.

Replacement is limited to selected paths and mutual same-rule/version siblings.
It requires a matching stable planner action/cost identity, explicit
`origin: "recovery_planner"`, `essential: false`, a date today or later in the
case zone, exactly integer zero `fulfilled_cents` and explicit empty
`actual_event_ids`. Essential action commitments require finance review, rather
than being deleted. Actual-linked, partially spent, undated, historical or
stale-owned commitments require reconciliation and are preserved. Ordinary
essential expenses and unrelated action/program commitments remain unchanged.
No selection changes actual balances, aid stage, support, or spending history.
The eventual finance consumer must retain selected essential flags/priority and
stamp ownership after authorization; user/model metadata cannot grant ownership.

## Precise assembly instructions — CaseService owner

1. Review/freeze the proposed records with P2. Merge the additive action fields
   (`dependency_links`, `priority`, dated `deadline`, `cost_items`), requirement
   reason additions and correction-history union into the authoritative shared
   definitions. Validate owned actions separately from preserved legacy records.
   Keep `0.1` only if the existing compatibility protocol permits it. No shared
   schema, command, server, agent, README or progress file was edited here.
2. Select authorized case evidence/confirmation/link records from the backend.
   Enforce household scope, trusted confirmation origin, reviewed predicate and
   source attribution; reject caller-selected household IDs/roles/provenance.
   `fact.correct` remains user-reported and cannot mint confirmation. A public
   page review alone is not household-specific approval. Establish the trusted
   writer before any public source-supported confirmation tool is exposed.
3. In the existing authorized CaseService revision transaction, read the exact
   snapshot/version and validated published catalog; call `evaluate_options`
   and `revise_plan`, then `resolve_dependencies` and `order_actions` with explicit
   backend time. Preserve extension metadata across revisions. In particular,
   update `revise_plan`'s existing strict validation to the merged action shape,
   retain priorities and terminal history, and retain links/costs/deadlines only
   for their exact matching current rule version. For a changed version retain
   the old metadata in the durable prior-state audit and request an explicit
   rebind/reconfirmation; never splice old links or cost support into new policy.
   Existing pure revision deliberately has not been rewired against an unfrozen
   shared shape in this branch.
4. Include evidence, confirmations, links, priorities, deadlines, cost records
   and correction history in revision replay fingerprints/invalidation. Today's
   fingerprint currently contains only facts, task status/inability and catalog;
   it must not suppress new input changes. Reassess affected programs and active
   transitive consumers; preserve unrelated and terminal records with scoped
   freshness. Do not let revising one program refresh another's stale inputs.
5. Add the reviewed correction form to `task.update` validation/dispatch as a
   mutually exclusive payload; normal completed/skipped/inability forms retain
   their existing behavior. Resolve accepted-event replay/fingerprint and expected
   case version first. Supply occurrence/receipt times and call
   `correct_completion` on a detached plan. Enforce active run/deadline for agent
   calls. On retained-history capacity/missing-reference failure return
   clarification rather than deleting history; later audit-backed resolution can
   recover the original report through CaseService.
6. Commit once through the existing transaction: proposed plan/metadata,
   authoritative source/confirmation changes if separately authorized, one case
   version, updated receipt time and prior-snapshot/event audit. For dependency,
   priority or cost revisions, increment the committed plan version once;
   `correct_completion` already increments its proposed plan version. Mark
   finance/affected derived outputs pending without editing the ledger. Validate
   full snapshot and compact result before commit; recheck lease/deadline and
   rollback all writes on validation/storage failure.
7. Invoke the reviewed C08 consumer with the plain cost export and an explicitly
   reconciled synthetic/authorized ledger. Require unchanged input case and plan
   versions before saving a comparison/scenario. Finance validates the full
   ledger, null/timing semantics, actual matches and forecast; the selection
   proposal is not `forecast_finances`' currently additive scenario shape. Do not
   pass it to that API without a reviewed replacement adapter. Keep a scenario
   hypothetical and commit its result through CaseService only.
8. Extend compact summaries, agent result schemas, public controls and replay
   regressions after the schema freeze. Current strict shared summaries do not
   expose the new detailed costs/links/correction fields. Add synthetic atomic
   conflict/rollback/restart/replay checks at the wrapper, then user-owned live
   proof and UI review. Existing live proofs remain passing historical evidence;
   no credentialed smoke was run for these new functions.

## Synthetic validation evidence

Focused command, without service/configuration or finance imports:

```sh
.venv/bin/python -W error::ResourceWarning -m unittest tests.test_planner_bounded -q
```

**40 focused checks pass.** They use detached plans derived from the existing
published-catalog evaluator/revision functions, synthetic attributed sources,
evidence/confirmation records and synthetic finance commitments. They cover
positive/negative/null availability; wrong-household/type/version/leaf/duplicate
links; unsupported/stale/conflicting/future/expired confirmations and sources;
AND/OR suppression; exact historical completion, missing/future reports;
missing/version-mismatched/stale dependencies; self/two-action cycles;
priority/deadline/dependency ordering; completion reference/timing/replay/capacity
and consumer invalidation; known/zero/null costs, provenance/timing/date bounds;
alternative exclusivity; actual/partial/essential/past/unknown cost preservation;
unrelated program/expense preservation; determinism, JSON and alias isolation.

The final focused evaluation/lifecycle/rule/pinned-Strands regression passes
**148 checks** (108 existing +40 new). The proposed schema and representative
plan/action/cost-export/selection outputs also pass Draft 2020-12 validation.

An earlier broader checkout run discovered **576 checks and passed all 571 selected
non-HTTP checks**, with no selected skips. After additional concurrent changes,
the latest broad run discovers **610 checks**: **603 of 605 selected non-HTTP
checks pass; two shared fixture checks error**. Both failures were independently
reproduced and traced to `invalid_input` at `$.finance.baseline`: these preexisting
fixtures inject only `{"input_case_version": N}` as a calculated baseline, which
current shared validation rejects. Affected checks:

- `test_case_service.CaseServiceTests.test_correction_retains_completed_work_and_marks_old_results_pending`
- `test_intake.IntakeTests.test_partial_updates_preserve_prior_facts_needs_and_completed_work`

No planner domain function is called by those fixture transitions; their command
returns a null snapshot after the shared finance-shape rejection. Shared schema,
CaseService/intake fixtures and commands are outside this task's ownership and
were left untouched. The shared owner must update those fixtures/compatibility
behavior and rerun before claiming the entire current checkout passes. This is a
remaining assembly regression gate, not a planner pass claim.

Counts include concurrent work from other owners and describe their specific
checkout snapshots rather than a shared tracker update. Five HTTP checks remain
excluded under the established loopback limitation. The earlier user-run
330-check/HTTP result remains historical evidence, not a new result here.
Expected provider-failure fixture log lines do not indicate an additional failure.
Reproduce the broad selection:

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

Existing uncommitted/shared/finance/frontend work was preserved. No private
environment or credential file was read or loaded, no real source/provider call
or credential smoke ran, and no model/configuration change was made. The MVP
excludes a second persistence layer, a finance optimizer, document uploads,
automatic agency decisions, external submission and new application workflows.
