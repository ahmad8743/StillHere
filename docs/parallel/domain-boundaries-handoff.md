# Deterministic cross-domain backend boundaries

October 11, 2026. Integration owner retains all durable writes and shared files.
Only `backend/stillhere/boundaries/`, `tests/test_domain_boundaries.py`,
`contracts/parallel/domain-boundaries.schema.json`, and this handoff are owned.
Existing uncommitted work was preserved. No private configuration, AWS files or
secrets were opened, searched or loaded. No network, agency, model, deployment,
frontend, Plaid or welfare-outreach operation ran.

| Readiness axis | State | Evidence / gate |
| --- | --- | --- |
| Executable deterministic boundary slices | READY_FOR_INTEGRATION | 44 focused synthetic checks pass; final combined evidence below |
| Integrated C01/C02/C05/C06/C08 acceptance | PENDING | Exact shared proposals below require review/application, durable scenario tests and adapter assembly |
| Live boundary verification | NOT_REQUIRED | These functions perform no model/provider operations |
| Agent adapter / Bedrock verification | PENDING | Separate user-run provider proof after shared integrated acceptance; prior bounded live evidence remains historical |
| Agency verification/provider | UNAVAILABLE | Backend selector interface only; default empty/fail-closed; no acquisition implementation |

No full-component or production-readiness claim follows from this slice.

## Reviewed domain rules

The planner, finance and application handoffs are proposal boundaries, not
accepted durable contracts. This adapter imports their authoritative Python
validators/calculations; JSON Schema alone cannot validate scope, reference
identity, calendar semantics, accounting, graph structure, stage correction or
trust. Current functions return detached proposals and perform no writes.

Cost reconciliation re-exports the actual validated plan. The caller never
supplies a model-generated export or arithmetic result. It validates the full
ledger through the unchanged finance engine, then validates the assembled
comparison through `validate_financial_scenario`. Essentials, actual/proposed
matches, support references, completed/skipped spending, restricted money,
unknown/partial fulfillment, historical timing and unrelated commitments are
retained. Only reciprocal, same-rule/version siblings are exclusive. Removal
also requires exact stable planner action/cost identity, explicit backend-owned
origin, **exact rule_id/rule_version**, explicit integer zero fulfillment and
an empty actual-event link list. Legacy commitments without those bindings
require reconciliation. Never manufacture the missing bindings from titles.

A dated null amount remains null and gives an incomplete hypothetical forecast.
A null date remains in the export and suppresses the entire executable
comparison. Unknown/stale/unverified quotes never become zero. Past costs and
protected references yield clarification. A refreshed untouched selected cost
gets a distinct deterministic `scenario_cost_*` identity plus
`planner_commitment_id`, because finance prohibits reuse of a baseline ID even
when replacing it. The comparison ledger is **hypothetical**, never a replacement
for the actual ledger. No savings, receipts or aid availability are inferred.

`validate_saved_action_scenarios` revalidates stored cost snapshots against the
current action/cost domain input. It never silently reprices a saved assumption.
Changed, stale, undated or now-past quotes require an explicit new `scenario.set`
and keep prior calculations pending. A hypothetical-only scenario change does
not by itself invalidate actual baseline money or trigger a baseline funding
gap; actual-input changes and incomplete baselines do request planner review.

Finance reassessment is recomputed from the ledger. Previous calculations must
be accepted backend bundles, not household/model projections. Requests identify
the case, input and plan versions, all changed finance references, exact affected
active current action IDs and preserved terminal IDs. Money/actual-record
changes request review even if totals stay equal: restrictions/accessibility can
change without a balance change. The stable request ID hashes the canonical
current calculation and versioned decision; list order cannot duplicate it.
Requests are advisory: they do not revise, complete or select actions.

Dependency evaluation and ordering use the planner's typed, version-pinned
graph validator. Missing links remain unknown; cycles remain explicit blockers.
Completion correction references the latest retained report, keeps its original
event and timestamps, appends a distinct correction, marks active transitive
consumers stale, and returns a pending plan proposal. Other completed/skipped
reports remain intact. No expense reversal occurs: any actual accounting
correction is a separate explicit finance operation.

Application invalidation matches published fact keys (plus issuing jurisdiction),
exact rule IDs, evidence IDs/requirement keys and attributable source IDs. It
marks only affected preparation pending. Reported stages, agency outcomes,
original history, answers/checklists and evidence observations remain retained.
An evidence availability report remains independent of changing acceptance
policy; `affected_evidence_ids` names acceptance review, not a deletion of that
availability report. Target version is proposal metadata, not a rewritten
historical preparation input version.

`report_application_only` accepts stage/correspondence metadata while rules are
unavailable. It validates retained graph/reference/audit identity and applies
the existing authoritative stage-transition/correction rules. Preparation stays
pending; prepared_at/input_case_version still describe the retained draft.
Its next step explicitly requests current official review. Original answers and
call script remain retained pending material, not fresh instructions. Evidence
edits in this mode require a separate current-rule retry; the combined intent is
rejected atomically rather than partly saved. A reported approval, or even a
synthetic backend-verified approval, creates neither received money nor computed
household eligibility. Report-only updates preserve any prior agency outcome
without claiming it was newly verified.

Available rule results always go through application-domain validation. Invalid
available references never silently fall back to report-only. Missing rules, or
a valid nonavailable result matching operation program/version/time scope, use
the explicit report-only path. Backend acquisition failures should map to this
path only through the typed unavailable error; programming/validation errors
remain errors.

## Callable signatures

Import these from `backend.stillhere.boundaries`:

```python
reconcile_action_costs(
    plan, ledger, selected_action_ids, *, input_case_version,
    as_of, time_zone, start_date,
) -> dict  # CostReconciliation

validate_saved_action_scenarios(
    plan, ledger, *, input_case_version, as_of, time_zone, start_date,
) -> dict  # SavedActionScenarioValidation; never changes saved quotes

finance_planner_request(
    plan, ledger, previous_forecasts, *, case_id, input_case_version,
    changed_record_ids, start_date, time_zone,
) -> dict  # PlannerReassessmentRequest; calculates current baseline

assemble_dependencies(
    plan, *, case_id, input_case_version, links, evidence, as_of,
    confirmation_ids=None, trusted_boundary=None, priorities=None, deadlines=None,
) -> dict  # authoritative planner plan proposal; no version increment

propose_completion_correction(
    plan, payload, *, event_id, occurred_at, received_at, input_case_version,
) -> dict  # CompletionCorrectionProposal; plan version +1, target case version +1

invalidate_applications(
    snapshot, *, target_case_version, changed_fact_keys=None,
    changed_rule_ids=None, changed_evidence_ids=None, changed_source_ids=None,
) -> dict  # ApplicationInvalidationProposal; no reports/evidence erased

report_application_only(
    snapshot, arguments, *, event_id, occurred_at, received_at,
) -> dict  # ApplicationBoundaryResult, mode=report_only

update_application_boundary(
    snapshot, arguments, rule_result, *, event_id, occurred_at,
    received_at, receipt_ids=None, trusted_boundary=None,
) -> dict  # ApplicationBoundaryResult, current_rules or report_only

TrustedRecordBoundary(*, resolver=None)
# Backend-only resolver(case_id, kind, record_ids) -> {records: [...], sources: [...]}
# kind: planner_confirmation | application_receipt

validate(definition_name, proposal)  # additive shape validation only
```

`FinanceInputError` and `InvalidInput` carry fixed messages/field paths.
CaseService maps malformed data to rejection; protected/unknown dates, unsupported
evidence edits during rule outage and missing audit capacity to clarification;
input-version races to conflict. There is no hidden clock or fallback date.
All timestamps and versions are backend context, never model authority.

Bounds inherit planner 32 retained actions, 128 links/evidence/confirmations,
32 nodes per action/eight graph levels/16 costs per action, application 64 history
and 32 correspondence, finance 256 records/three scenarios, plus a 2 MB boundary
input envelope. Capacity failures retain prior history. The retained application
DAG uses memoized heights so shared subgraphs cannot cause exponential work.

## Trusted confirmation contract

The wrapper accepts **IDs through backend context**, never confirmation/receipt
records through household/model arguments. A Python backend-created
`TrustedRecordBoundary` selects durable authorized/verified records and supporting
sources. The callback itself is the trusted configuration boundary; JSON labels,
source URLs, IDs or a deserialized dict cannot instantiate its authority.
No resolver means requested nonempty IDs fail closed; empty IDs provide no
verification. Tests use an explicitly synthetic backend callback only.

Planner still checks exact case/action/rule/version/node, Boolean value,
reviewed requirement-attributed public sources, observation/expiry and conflicts.
Trusted selection does not bypass those checks. Application receipts additionally
require backend-selected current nonfuture/unexpired sources, exact household /
application / program scope, matching issuer and agency-record verification;
the application validator enforces stage/time/reference semantics. Public pages
and household correspondence cannot establish individualized verification.
Do not register this class, callback, receipt IDs or confirmation IDs in tool
arguments. No live agency ingestion, correction/retraction or provider exists.
The current prepare path must retain empty `agency_receipts`; any future
receipt-bearing preparation must use the same backend selector and source checks.

CaseService must also reserve planner financial ownership metadata. Household
`finance.update` must not mint `origin`, `planner_cost_id`, `planner_commitment_id`,
`rule_id`, `rule_version`, `actual_event_ids` or other backend provenance. The
exact shared validation patch below reserves these names. Already-existing
unreviewed metadata needs owner reconciliation; labels alone prove no ownership.

## CaseService transaction and effect contract

Authorize session/case first, resolve `(case_id,event_id)` logical replay before
version checks, then validate expected version/run lease/deadline. Recompute
proposals from the transaction's authorized inputs. Commit only accepted
application/evidence or plan/scenario fields, one case version, original event
result and before/after audit in the same transaction. A clarification/conflict
commits none of those domain effects. A calculated hypothetical ledger is never
committed as actual money. Replayed events return their original acceptance and
latest authorized snapshot without invoking correction/reassessment again.

The shared patch enqueues a finance request in `planner_effects` with unique
`(case_id,request_id)`, target input version, plan version and request JSON in the
same CaseService transaction. The completion owner must implement the internal
consumer before claiming integrated reassessment:

```python
CaseService.complete_planner_effect(
    case_id, request_id, *, expected_case_version, expected_plan_version,
    # backend-derived worker/run authority; never an HTTP household payload
) -> accepted | superseded | conflict
```

Within that method: reselect the queued request and scoped current snapshot;
reject/supersede mismatched case or plan versions; re-evaluate published rules
for the explicitly affected programs, preserving terminal/unrelated work; bind
only exact current links/costs/evidence; invoke `assemble_dependencies` then
ordering; validate snapshot and commit plan/version/audit plus effect completion
once. On later-version input create the new canonical request, never relabel an
old one current. An unchanged effect remains queued without a second model run.
Model availability is not a requirement for this deterministic worker.

Plan revision fingerprints must include fact/evidence inputs, typed links,
trusted confirmation IDs plus verified revisions, exact costs, priorities,
deadlines, task history and published catalog version. Retain links/costs/order
metadata only when the revised action's exact rule/version matches; changed
policy requires explicit rebind and preserves old metadata in durable audit.
The existing revision function's fact-only fingerprint/metadata behavior remains
an integration blocker; this slice does not rewrite the planner package.

Rule publication and evidence-source expiry must enqueue case-scoped invalidation
using `invalidate_applications(...changed_rule_ids/changed_source_ids...)` through
the same owner transaction. The fact/evidence command patches are concrete;
the rule-publication fanout lifecycle still needs the integration owner. A rule
version migration requires explicit re-preparation preserving report/history.

## Exact shared Python patches for owner review

These diffs were generated against the preserved shared checkout and compile in memory. They have **not** been applied or accepted. Apply the schema proposal below first. Rebase against concurrent changes rather than replacing whole shared files. Durable restart/rollback/lease acceptance remains pending.

### backend/stillhere/commands.py

```diff
--- a/backend/stillhere/commands.py
+++ b/backend/stillhere/commands.py
@@ -3,7 +3,7 @@
 import copy
 import hashlib
 
-from .contracts import validate
+from .contracts import InvalidInput, validate
 
 
 def user_fact(value, observed_at):
@@ -70,6 +70,15 @@
 
 
 def _task_update(snapshot, payload, occurred_at, received_at=None, event_id=None):
+    if "completion_event_id" in payload:
+        from .boundaries import propose_completion_correction
+        proposal = propose_completion_correction(
+            snapshot["plan"], payload, event_id=event_id,
+            occurred_at=occurred_at, received_at=received_at,
+            input_case_version=snapshot["case_version"],
+        )
+        snapshot["plan"] = proposal["plan"]
+        return
     from .planner.tasks import record_task
     record_task(snapshot, payload, occurred_at, received_at, event_id)
 
@@ -96,6 +105,21 @@
 
 def validate_payload(command_type, payload):
     validate(COMMAND_HANDLERS[command_type][0], payload)
+    if command_type == "finance.update":
+        reserved = {"origin", "planner_cost_id", "planner_commitment_id", "rule_id",
+                    "rule_version", "actual_event_ids", "verification_state"}
+        def reject_reserved(value, depth=0):
+            if depth > 8:
+                raise InvalidInput("$.payload", "Financial metadata exceeds the bounded depth.")
+            if isinstance(value, dict):
+                if reserved & value.keys():
+                    raise InvalidInput("$.payload", "Backend ownership and verification fields cannot be household financial input.")
+                for child in value.values():
+                    reject_reserved(child, depth+1)
+            elif isinstance(value, list):
+                for child in value:
+                    reject_reserved(child, depth+1)
+        reject_reserved(payload)
 
 
 def apply_command(snapshot, command, received_at):
@@ -117,6 +141,13 @@
     updated["updated_at"] = received_at
     changed_inputs = ({command["payload"]["fact_key"]} if command["type"] == "fact.correct"
                       else set(command["payload"]) if command["type"] == "intake.submit" else set())
+    if changed_inputs and updated["applications"]:
+        from .boundaries import invalidate_applications
+        invalidation = invalidate_applications(
+            updated, target_case_version=updated["case_version"],
+            changed_fact_keys=sorted(changed_inputs),
+        )
+        updated["applications"] = invalidation["applications"]
     resources = updated["resources"]
     search = resources.get("search")
     if search and changed_inputs & {search["query"]["location_scope"] + "_location", "requested_needs", "needs"}:
```

### backend/stillhere/integration.py

```diff
--- a/backend/stillhere/integration.py
+++ b/backend/stillhere/integration.py
@@ -28,7 +28,7 @@
             else:
                 start = command["payload"].get("start_date") or self._instant(now).astimezone(ZoneInfo(snapshot["time_zone"])).date().isoformat()
                 try:
-                    alternatives = self._finance_alternatives(snapshot, command["payload"]["scenario"].get("alternative_ids", []), now)
+                    alternatives = self._finance_alternatives(snapshot, command["payload"]["scenario"].get("alternative_ids", []), now, start_date=start)
                 except InvalidInput as error:
                     return snapshot, self._result(command["event_id"], "needs_clarification", now, snapshot, issue={"code": "action_costs_unresolved", "field": error.field, "message": str(error), "retryable": False})
                 proposed = set_financial_scenario(ledger, command["payload"]["scenario"], event_id=command["event_id"],
@@ -55,15 +55,31 @@
             caller = Authority(snapshot["case_id"], "household", "household_" + owner[:32], permissions, True)
             return self._apply_check_in_command(connection, snapshot, command, now, caller), None
         if command["type"] == "application.update":
-            from .applications import update_application
+            from .boundaries import invalidate_applications, update_application_boundary
             application = next((item for item in snapshot["applications"] if item["id"] == command["payload"]["application_id"]), None)
             if application is None:
                 raise InvalidInput("$.application_id", "Select a saved application in this case.")
-            rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
-            proposal = update_application(snapshot, command["payload"], rules, event_id=command["event_id"], occurred_at=command["occurred_at"], received_at=now)
+            from .service import ServiceError
+            try:
+                rules = self._application_rules(snapshot, application["program_id"], application["rule_version"], now)
+            except ServiceError as error:
+                if error.issue["code"] != "application_rules_unavailable":
+                    raise
+                rules = None
+            # MVP has no trusted agency provider. Receipt IDs/authority are never
+            # selected by this household payload; the boundary defaults empty.
+            proposal = update_application_boundary(
+                snapshot, command["payload"], rules, event_id=command["event_id"],
+                occurred_at=command["occurred_at"], received_at=now,
+            )
             snapshot["applications"] = [proposal["application"] if item["id"] == application["id"] else item for item in snapshot["applications"]]
             snapshot["evidence"] = proposal["evidence"]
-            if command["payload"].get("evidence_changes"):
+            if proposal["changed_evidence_ids"]:
+                invalidation = invalidate_applications(
+                    snapshot, target_case_version=snapshot["case_version"]+1,
+                    changed_evidence_ids=proposal["changed_evidence_ids"],
+                )
+                snapshot["applications"] = invalidation["applications"]
                 if snapshot["plan"]["state"] != "not_requested":
                     snapshot["plan"].update(state="pending", pending_input_case_version=snapshot["case_version"]+1)
                 if snapshot["finance"]["state"] != "not_calculated":
@@ -75,34 +91,35 @@
     def _instant(value):
         return datetime.fromisoformat(value.replace("Z", "+00:00"))
 
-    def _finance_alternatives(self, snapshot, selected_ids, now):
-        from .planner.costs import export_action_costs, propose_alternative_selection
+    def _finance_alternatives(self, snapshot, selected_ids, now, *, start_date):
+        from .boundaries import reconcile_action_costs
         if not selected_ids:
             return []
-        exported = export_action_costs(snapshot["plan"], input_case_version=snapshot["case_version"], as_of=now, time_zone=snapshot["time_zone"])
-        proposal = propose_alternative_selection(exported, selected_ids, existing_commitments=snapshot["finance"]["ledger"]["expense_commitments"])
+        proposal = reconcile_action_costs(
+            snapshot["plan"], snapshot["finance"]["ledger"], selected_ids,
+            input_case_version=snapshot["case_version"], as_of=now,
+            time_zone=snapshot["time_zone"], start_date=start_date,
+        )
         if proposal["state"] != "proposed":
-            raise InvalidInput("$.scenario.alternative_ids", "Reconcile current path selection and explicit dated costs before comparing; unknown costs remain unknown.")
-        alternatives = []
-        for identifier in selected_ids:
-            individual = propose_alternative_selection(exported, [identifier], existing_commitments=snapshot["finance"]["ledger"]["expense_commitments"])
-            costs = copy.deepcopy(individual["add_commitments"])
-            # Domain export ownership metadata remains a trusted backend input.
-            for cost in costs:
-                if cost["date"] is None or cost["amount_cents"] is None:
-                    raise InvalidInput("$.scenario.alternative_ids", "An action comparison requires known costs and explicit dates.")
-                if cost.get("due_at") is None:
-                    cost.pop("due_at", None)
-                cost.update(origin="recovery_planner", fulfilled_cents=0, actual_event_ids=[])
-            action = next(item for item in snapshot["plan"]["actions"] if item["id"] == identifier)
-            alternatives.append({"id": identifier, "label": action["title"], "costs": costs, "replaces_commitment_ids": individual["remove_commitment_ids"]})
-        return alternatives
+            raise InvalidInput("$.scenario.alternative_ids",
+                "Reconcile dated costs, protected commitments and current path selection before comparing.")
+        return proposal["action_alternatives"]
 
     def _refresh_finance(self, snapshot, now, event_id, *, start_date=None, input_version=None, changed_ids=()):
         from .finance import compare_financial_scenarios, finance_reassessment, prepare_forecast_publication
         version = snapshot["case_version"] if input_version is None else input_version
         start_date = start_date or self._instant(now).astimezone(ZoneInfo(snapshot["time_zone"])).date().isoformat()
         prior = copy.deepcopy(snapshot["finance"])
+        from .boundaries import validate_saved_action_scenarios
+        from .finance import FinanceInputError
+        saved_check = validate_saved_action_scenarios(
+            snapshot["plan"], snapshot["finance"]["ledger"],
+            input_case_version=snapshot["case_version"], as_of=now,
+            time_zone=snapshot["time_zone"], start_date=start_date,
+        )
+        if saved_check["state"] != "current":
+            raise FinanceInputError("$.finance.scenarios",
+                "Saved action costs need explicit scenario refresh; prior calculations remain pending.")
         forecasts = compare_financial_scenarios(snapshot["finance"]["ledger"], start_date=start_date,
                     time_zone=snapshot["time_zone"], input_case_version=version)
         validate("C08ForecastBundle", forecasts)
@@ -110,10 +127,24 @@
         validate("C08CurrentFinance", published["proposed_finance"])
         reassessment = finance_reassessment(prior if prior.get("baseline") else None, forecasts, changed_record_ids=changed_ids)
         validate("C08FinanceReassessment", reassessment)
-        snapshot["finance"] = {**published["proposed_finance"], "ledger": snapshot["finance"]["ledger"], "reassessment": reassessment}
-        if reassessment["required"] and snapshot["plan"]["state"] != "not_requested":
-            # Financial constraints request a new evaluation; terminal work is retained.
-            snapshot["plan"].update(state="pending", pending_input_case_version=version, finance_reassessment=copy.deepcopy(reassessment))
+        from .boundaries import finance_planner_request
+        previous_bundle = ({key: prior[key] for key in
+                            ("contract_version", "input_case_version", "baseline", "scenarios")}
+                           if prior.get("baseline") else None)
+        request = finance_planner_request(
+            snapshot["plan"], snapshot["finance"]["ledger"], previous_bundle,
+            case_id=snapshot["case_id"], input_case_version=version,
+            changed_record_ids=list(changed_ids), start_date=start_date,
+            time_zone=snapshot["time_zone"],
+        )
+        snapshot["finance"] = {**published["proposed_finance"], "ledger": snapshot["finance"]["ledger"],
+                               "reassessment": reassessment, "planner_request": request}
+        if request["required"] and snapshot["plan"]["state"] != "not_requested":
+            snapshot["plan"].update(state="pending", pending_input_case_version=version,
+                                   finance_reassessment=copy.deepcopy(request))
+            for action in snapshot["plan"]["actions"]:
+                if action["id"] in request["affected_action_ids"]:
+                    action["input_freshness"] = "stale"
 
     def _application_rules(self, snapshot, program_id, version, now):
         from .knowledge import ProgramRuleStore
@@ -127,6 +158,13 @@
 
     def _init_integration(self, connection):
         connection.executescript("""
+            CREATE TABLE IF NOT EXISTS planner_effects (
+                case_id TEXT NOT NULL REFERENCES cases(case_id),
+                request_id TEXT NOT NULL, input_case_version INTEGER NOT NULL,
+                plan_version INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
+                request_json TEXT NOT NULL,
+                PRIMARY KEY (case_id, request_id)
+            );
             CREATE TABLE IF NOT EXISTS operators (
                 token_digest TEXT PRIMARY KEY, operator_id TEXT NOT NULL UNIQUE,
                 created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1
```

### backend/stillhere/service.py

```diff
--- a/backend/stillhere/service.py
+++ b/backend/stillhere/service.py
@@ -257,6 +257,15 @@
             validate("CaseSnapshot", snapshot)
         else:
             snapshot = apply_command(snapshot, command, now)
+        request = snapshot["finance"].get("planner_request")
+        if (request and request["required"] and request["affected_action_ids"]
+                and request["input_case_version"] == snapshot["case_version"]):
+            connection.execute(
+                "INSERT OR IGNORE INTO planner_effects "
+                "(case_id,request_id,input_case_version,plan_version,request_json) VALUES (?,?,?,?,?)",
+                (snapshot["case_id"], request["request_id"], request["input_case_version"],
+                 request["plan_version"], canonical_json(request)),
+            )
         connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), command["case_id"]))
         connection.execute(
             "UPDATE events SET applied_version=?, applied_received_at=?, before_fact_json=?, before_case_json=? WHERE case_id=? AND event_id=?",
```

## Exact shared schema proposal

Use this function in the integration owner's schema assembly. It returns a detached in-memory schema; save it only after owner review. It passed Draft 2020-12 validation plus representative shared-validator tests for costs, requests, reports and strict mutually exclusive completion corrections. No shared schema file was written. `contracts.py` needs no implementation patch: its existing validator accepts these merged definitions; semantic validation stays in the domain functions.

```python
import copy
import json
from pathlib import Path


def proposed_shared_schema(current, contract_root):
    """Owner review only: return a detached schema; never write the shared file."""
    result = copy.deepcopy(current)
    prefixes = {'planner': 'C05', 'applications': 'C06', 'finance': 'C08', 'domain-boundaries': 'B01'}
    def rewrite(value, domain):
        if isinstance(value, dict):
            output = {key: rewrite(child, domain) for key, child in value.items()}
            reference = value.get('$ref')
            if reference:
                if reference.startswith('#/$defs/'):
                    output['$ref'] = '#/$defs/' + prefixes[domain] + reference.split('/')[-1]
                elif reference.startswith('../case-service.schema.json#/$defs/'):
                    output['$ref'] = '#/$defs/' + reference.split('/')[-1]
                else:
                    file, definition = reference.split('.schema.json#/$defs/')
                    output['$ref'] = '#/$defs/' + prefixes[file] + definition
            return output
        if isinstance(value, list):
            return [rewrite(child, domain) for child in value]
        return value
    # Proposed handoffs remain a review boundary. Adopt these complete copies
    # only after reviewing each additive definition and compatibility change.
    for domain, prefix in prefixes.items():
        proposal = json.loads((contract_root/'parallel'/(domain+'.schema.json')).read_text())
        for name, definition in proposal['$defs'].items():
            result['$defs'][prefix+name] = rewrite(definition, domain)
    result['$defs']['RecoveryPlanAction'] = {'$ref':'#/$defs/C05PlannerAction'}
    task = result['$defs']['TaskUpdatePayload']
    correction_ref = {'$ref':'#/$defs/C05PlannerCompletionCorrection'}
    if correction_ref not in task['anyOf']:
        task['anyOf'].append(correction_ref)
    task['properties'].update({
        'completion_event_id':{'$ref':'#/$defs/Id'},
        'reason_code':{'enum':['reported_in_error','not_completed','wrong_action']},
    })
    result['$defs']['CaseSnapshot']['properties']['finance']['properties']['planner_request'] = {
        'anyOf':[{'$ref':'#/$defs/B01PlannerReassessmentRequest'},{'type':'null'}]}
    return result


```

## Other shared-file proposals and overlapping work

`contracts.py`: zero code delta; adopt the reviewed merged definitions and keep
domain semantic checks. `server.py`: zero route delta; existing household command
dispatch accepts the reviewed payload after shared schema/command validation.
No new confirmation/agency endpoint or household authority field is proposed.
Existing agent files remain under their owner; register only intent arguments,
and inject these calls through CaseService after its transaction acceptance.

`README.md` proposed exact addition (owner placement after local verification):

```markdown
The deterministic cross-domain adapter handoff is in
docs/parallel/domain-boundaries-handoff.md. Its pure slices are ready for review;
shared integration and new live adapter proof remain pending. Run the focused
synthetic suite with `.venv/bin/python -m unittest tests.test_domain_boundaries`.
CaseService is the only durable writer. Unknown costs/dates and unreceived aid
remain unknown/unreceived; no agency provider or external submission is enabled.
```

Shared progress / backend integration ledger proposed exact row (owner adds it
without upgrading the domain-component or deployment rows):

```markdown
| Domain boundaries | Pure slices READY_FOR_INTEGRATION; 44 focused / 357 combined checks pass | Shared patches reviewed only in isolated synthetic simulation; installed acceptance PENDING | Deterministic model proof NOT_REQUIRED; new adapter Bedrock proof PENDING |
```

The user-authorized coordination messages went to **Build household agent
adapters** on October 11. Its `domain-dependencies.patch` overlaps the scenario
and application hunks here; the integration owner must compose a single patch,
not apply both replacements blindly. Use this handoff's ownership reservations,
exact rule-bound cost replacement, saved-quote freshness check, application
invalidation, completion correction and deduplicated request additions. Retain
the adapter owner's provider/schema/run controls and separate no-car synthetic
fixture proposal. A synthetic local cost fixture does not verify a real fee.
The owner's new service fixture should pass an explicit date with null amount.

## Final reproducible deterministic evidence

Run from the repository root; these commands clear the inherited environment
and never load private configuration or an AWS credential chain:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest \
  tests.test_domain_boundaries -q

env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest \
  tests.test_domain_boundaries \
  tests.test_finance tests.test_finance_updates tests.test_finance_scenarios \
  tests.test_finance_schema tests.test_planner tests.test_planner_bounded \
  tests.test_plan_lifecycle tests.test_applications -q
```

Final result: **44 focused checks pass; 357 combined checks pass**. Independent
Draft 2020-12 schema and representative output validation uses only registered
in-memory schemas. Shared proposal schemas also validate in memory. No HTTP,
full-checkout, installed-assembly, live-provider or production result is claimed.

One focused check applies the delivered diff and schema **in a child process**,
using disposable synthetic cases/database. It verifies dated-null hypothetical
comparison, unchanged actual money, scenario replay, actual-input reassessment,
one durable planner-effect enqueue across retries, rejection of forged household
planner ownership, rule-outage report-only approval without money, subsequent
fact invalidation and completion correction with original audit/replay retained.
It makes no shared-file changes. This simulation caught and fixed an incorrect
exception-field assumption before handoff. After owner application/rebasing,
update/retire this patch-text simulation and add equivalent installed-service
acceptance tests; success here is review evidence, not integrated readiness.

The pure tests additionally verify all four canonical finance outcomes,
restriction preservation, unknown/zero/dates, source expiry, same-rule sibling
selection, protected actual/fulfilled/support spending, no-car replanning with
retained completed history, malformed/current/stale rules, stale saved quotes,
application approval with no receipts, explicit trusted receipt scope and
household forgery rejection, bounds, determinism and input/output alias isolation.

## USER-RUN provider commands and assertions

After shared integrated acceptance, the user can run the adapter owner's existing
executable harness using their configured model/region. Codex did not run it or
load the private configuration:

```sh
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode all --run-live --env-file .env.local
```

Omit `--env-file` if the user's process configuration and external AWS credential
chain are already configured. The harness uses disposable synthetic cases.
Required assertions: successful real new-tool invocations; a complete saved
reply grounded in deterministic finance results; 1,200-cent actual spending
applied once; baseline actual money distinct from hypothetical receipts;
application submission remains a household report with no agency/money creation;
no-car online route remains provisional while office access is blocked; dated
null costs stay incomplete/null; no task, consent, location or outreach inferred;
reopened CaseService reads match; replay is `already_applied` with unchanged
snapshot, no duplicate effects and no new model run. Missing shared wiring or
any failed assertion exits nonzero and leaves live verification pending.
Return only the harness's sanitized labels/assertions/counts and exit result.
The pure boundary functions themselves require no live-model proof.

## MVP blockers versus later extensions

MVP integration blockers:

- Review/adopt the proposed shared schemas and compose the overlapping owner
  patches; preserve existing command forms and reject new authority fields.
- Run installed CaseService scope/version/replay/restart/rollback and active-run
  acceptance for the command, scenario and derived-result paths. Test rule
  outage with a report/correspondence and with an unsaved combined evidence edit.
- Implement the deterministic planner-effect consumer, scoped invalidation and
  refreshed revision fingerprint/metadata retention. Enqueue alone is not a
  completed reassessment. Verify completed/unrelated records remain preserved.
- Integrate rule publication/source expiry invalidation, explicit rule-version
  re-preparation and normalized evidence creation through CaseService. Keep
  stale answers, sources and cost snapshots pending until correctly refreshed.
- Record case/plan input revisions with stored scenario quotes and recheck them
  inside the commit transaction. Accept explicit quote refresh; do not silently
  substitute current prices into a saved hypothetical scenario.
- Complete new adapter synthetic/SDK acceptance, then receive user-run Bedrock
  evidence. Do not deploy before integrated acceptance.

Later extensions:

- Wider official policy coverage, eligibility/fee/effective-date review and
  non-Boolean form-field mapping; partial graphs remain provisional now.
- Agency acquisition, scoped verifier provisioning, retraction/correction and
  private-source retention policy. MVP defaults to no agency integration.
- Evidence/document content, OCR/uploads, correspondence retraction, installment
  accounting, support remapping across alternative paths and durable archival
  past bounded inline history. None is silently implemented by these adapters.

Frontend, Plaid, live welfare outreach and deployment are outside this slice.
