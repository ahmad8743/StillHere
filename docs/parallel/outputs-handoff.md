# Output domain handoff

Date: October 11, 2026. Proposed contract version: `0.1`.

The independent **C02/C10 output validation slice is READY_FOR_INTEGRATION**.
This is slice readiness only. Full C02/C09/C10 readiness, frontend rendering,
CaseService publication, SDK structured-output wiring, and live Bedrock
verification are not established by these checks. No shared progress status was
changed. CaseService owns every durable publication and assistant-turn write.

Owned artifacts:

- `backend/stillhere/outputs/`: standard-library-only builders and validators.
- `tests/test_outputs.py`: synthetic finance, application, plan and check-in
  snapshots; no dependency on those domain implementations.
- `contracts/parallel/outputs.schema.json`: separate proposed definitions, not
  a modification to the shared case-service schema.
- This handoff. Shared services, commands, agent, server, frontend, README and
  progress documents were left to their owners.

## API and publication boundary

All functions accept ordinary JSON data and have no database, network, provider,
environment-loading or clock-reading side effects. `now` is an explicit backend
RFC 3339 UTC instant. Snapshot identity is checked but **authorization is a
caller precondition**: supply the current snapshot obtained under the authenticated
household session, never a model-supplied snapshot. IDs are not access grants.
Outputs and their nested arrays are detached from inputs.

```python
from backend.stillhere.outputs import (
    build_dashboard_descriptor,
    prepare_dashboard_publication,
    validate_dashboard_publication,
    build_follow_up_question,
    prepare_structured_reply,
    validate_structured_reply,
)

# snapshot and now come from trusted application context.
descriptor = build_dashboard_descriptor(
    snapshot, component_id="component_tasks", kind="task_list",
    record_ids=[], display_order=0, now=now,
)
prepared = prepare_dashboard_publication(
    snapshot, {"components": [descriptor]}, now=now,
)
# Inside the eventual CaseService transaction, after reauthorizing and reading:
validated = validate_dashboard_publication(latest_snapshot, prepared, now=commit_time)
# Only CaseService may now commit validated["components"] and metadata.

question = build_follow_up_question(
    question_id="question_transport", prompt="Do you have transport for this step?",
    kind="single_choice", choices=[
        {"id": "choice_yes", "label": "Yes"},
        {"id": "choice_unsure", "label": "Unsure"},
    ],
)
reply = prepare_structured_reply(
    snapshot, {"text": "We can work with what you know.", "questions": [question]},
    now=now,
)
validated_reply = validate_structured_reply(latest_snapshot, reply, now=commit_time)
```

`prepare_dashboard_publication` is the pure prepare boundary for the planned
`publish_dashboard_components` tool. There is no registered tool or public
command in this slice. `validate_dashboard_publication` checks the prepared
shape, case/version, age and original derived metadata against the supplied
snapshot, then returns newly derived metadata at commit time. Source expiry
between prepare and validation becomes visibly stale. Both functions return
`status: "prepared"`; neither reports a durable `applied` result.

`prepare_structured_reply` also accepts an existing plain string reply or
`{"text": "..."}`. Both normalize to a result with `questions: []`.
`validate_structured_reply` repeats all shape/text/question checks and the same
version/age checks. The backend still chooses assistant turn ID, role, state,
parent event, receipt time and active run. The result cannot choose those fields.

`OutputValidationError` exposes `code`, `field`, and a safe `issue` using the
existing `{code, message, field, retryable}` shape. Invalid proposals are rejected,
not truncated, silently reordered, partially published, or converted to a
successful empty result. Keep previously accepted content on rejection. Codes
include `invalid_output`, `output_limit`, `dangling_reference`, `reference_kind`,
`ambiguous_reference`, `stale_output`, and `invalid_preparation`. Error text does
not echo untrusted values or unexpected property names.

## Proposed schemas and compatibility

Select a named `$defs` entry in `contracts/parallel/outputs.schema.json`; the file
is a definition bundle like the shared contract. `validate_shape(name, value)`
uses this package's small schema vocabulary. It is a structural check; callers
must use the prepare/validate functions for cross-record and cross-field checks.
All objects disallow additional properties. The executable JSON Schema and
runtime semantic checks together define the boundary.

| Definition | Shape and use |
| --- | --- |
| `DashboardDescriptor` | Existing `{id, kind, record_ids, display_order}` shape; no new kinds or properties |
| `PublishDashboardArguments` | Model proposal `{components: DashboardDescriptor[]}` only |
| `RecordDisplayState` | `{record_id, freshness, state, availability, data_mode}` derived from existing records; last two fields nullable |
| `ComponentDisplayState` | `{component_id, freshness, state, record_states}` in descriptor order |
| `DashboardPublication` | `{contract_version, status, case_id, input_case_version, prepared_at, components, component_states}` internal prepare result |
| `DashboardOutputMetadata` | `{input_case_version, prepared_at, component_states}` proposed additive snapshot projection |
| `FollowUpChoice` | `{id, label}` only; display data without values, commands, URLs, defaults or authority |
| `FollowUpQuestion` | `{id, prompt, kind, choices, allow_skip: true}`; kind is `text`, `single_choice`, or `multiple_choice` |
| `StructuredReplyArguments` | `{text, questions?}` model proposal; existing string replies normalize to this shape |
| `StructuredReplyResult` | `{contract_version, status, case_id, input_case_version, prepared_at, text, questions}` internal prepare result |

The shared `DashboardDescriptor` already accepts every emitted descriptor.
`components: []` remains valid and may be an explicit replacement publication;
omitting a publication tool call should retain previous descriptors.

The proposed **additive shared fields are not installed**:

1. Optional `CaseSnapshot.dashboard_output: DashboardOutputMetadata`, paired
   with the existing `CaseSnapshot.components`. Metadata component IDs and order
   must correspond exactly to that descriptor array. Keep descriptors as the
   single source of selection/order. On reads, rederive time-dependent metadata
   from the authorized records; saved `prepared_at` cannot freeze source expiry.
2. Optional `ConversationTurn.questions: FollowUpQuestion[]` (maximum two),
   default absent/empty for legacy turns. Only a validated complete assistant
   turn carries questions. Retain the existing `text`, `role`, `state`, IDs,
   `created_at`, and failure `issue`. Do not assign the whole internal reply
   envelope to a turn.
3. For explicit answer correlation, proposed optional
   `ConversationMessagePayload.reply_to_turn_id: Id` and `question_id: Id`.
   Keep existing `choice_id: Id` for a single selection. For multiple selection,
   propose optional `choice_ids: Id[]` (one to six unique IDs), mutually exclusive
   with `choice_id`. These fields need shared schema/command review; they are not
   implemented here. Until then, single-choice can use the existing choice ID
   and text; multiple-choice answers can be submitted as ordinary user text.

The original strict shared schemas reject those extra fields. Concurrent shared
integration may add them independently; this slice does not own or certify those
edits. The integrator must add/review the optional definitions and update the
real/mock consumers together before persisting them. Existing
queued/running/failed/text-only turns need no migration.
There is no new public command type in this proposal.

IDs retain the existing opaque string shape and 128-character limit, with stricter
output hygiene: no whitespace, markup, hidden controls or active URI schemes.
Existing service-generated IDs satisfy that restriction. Displays must treat IDs
as opaque text, not selectors or URLs.

## Reference matrix

IDs must exist in the supplied authorized snapshot and have the matching domain.
An ID found in another collection is not a valid substitute. Indexed IDs are
unique across these collections; duplicates fail as ambiguous rather than
arbitrarily picking one. No IDs are manufactured for singleton sections.

| Component kind | Allowed persisted references | Empty selection |
| --- | --- | --- |
| `urgent_resource` | `resources.items[].id` | Rejected |
| `next_step` | `plan.actions[].id` | Rejected |
| `task_list` | `plan.actions[].id` | Allowed |
| `blocker_controls` | Action, need, evidence, or `plan.blockers[].id` | Allowed |
| `evidence_checklist` | `evidence[].id` | Allowed |
| `aid_tracker` | `applications[].id`, `finance.ledger.aid[].id` | Allowed |
| `finance_overview` | Ledger money sources, expense commitments, aid, support; existing `finance.baseline` identity | Allowed |
| `scenario_comparison` | `finance.scenarios[]` identities | Rejected |
| `check_in` | Schedule, last report, attempts and authorized `follow_ups[]` identities | Allowed |
| `source_details` | `sources[].id` | Allowed |

The finance baseline/scenarios may use `scenario_id` when `id` is absent. For
example, a stored baseline with `scenario_id: "baseline"` is referenceable;
`baseline: null` does not create a reserved record. Stored scenario definitions
with `id` also work. A scenario definition is not a computed scenario result;
render the actual record shape/state and show absent calculations as unknown.
No totals, gaps, dates, new financial records or forecasts are calculated here.

Legacy planner blockers/questions often have `node_id`, not a record `id`.
Those nodes are not indexed as dashboard records; reference the owning action
for its blocker controls. `plan.questions` do not automatically become assistant
questions. Records without stable IDs remain available in their domain section
but cannot be individually referenced.

`shared_location`, raw facts, actual financial events, conversation turns and
operator authority are not descriptor reference domains. The check-in card's
fixed location controls must use the separately authorized shared-location
projection and explicit user consent commands. No output enables sharing,
enrollment, acknowledgment, dispatch or external submission. General source
details must resolve persisted attribution, not accept a model-provided URL.

Empty/partial snapshots are supported: the identity/version fields are required;
omitted domain sections behave as empty. Present sections/collections must have
the expected object/array shape. Aggregate empty cards use the section's status
and unknown freshness; they do not create a zero balance, an enrolled schedule,
an approved application, a source, or a synthetic action. Empty resource searches
remain `not_requested`, `no_match`, or `unavailable` in the snapshot. An empty
urgent-resource card is rejected; the consumer must still display the snapshot's
retrieval notices/fallback UI when there are no resource descriptors.

## Bounds and state semantics

- At most 16 components, 24 unique record references per component, and 4,096
  scanned snapshot records. Display order is an integer from 0 through 1,023;
  descriptor arrays must already have strictly increasing unique orders. Gaps
  are allowed. Component IDs are unique within the publication.
- Reply text is nonblank and at most 8,000 characters. At most two questions,
  500 characters per prompt, and six choices with 160 characters per label.
  Choice questions require two to six choices; text questions have none.
  Question and choice IDs are unique across the whole reply. Skipping is always
  allowed; no preselected answer is accepted.
- Every proposed/prepared output has a 65,536-byte canonical ASCII JSON ceiling,
  2,048 value nodes, and eight levels of nesting. These aggregate budgets can
  reject combinations below individual field maxima. Excesses fail; no records
  or questions are silently dropped. Non-JSON types, nonfinite numbers, cycles,
  boolean/floating orders and version coercion are rejected.
- Plain text excludes angle brackets, backticks, active `javascript:`,
  `vbscript:` and `data:` schemes, control characters (except newline/tab), and
  bidirectional controls. There are no HTML/JS/template/widget fields. Consumers
  must still render text inertly, e.g. as text nodes, without markdown execution,
  `innerHTML`, event handlers, evaluation or dynamic component imports. Stored
  source/record bodies are not copied into output payloads and stay untrusted.
- Prepared output must match the supplied snapshot's case ID and exact case
  version. It expires after 300 seconds and cannot be future-dated. Both reply
  and dashboard validators reject a changed snapshot/version; prepare anew
  after case mutations. These are validation guards, not session authorization,
  signatures, replay storage or write leases.

Freshness is derived, never model-selected. Explicit `stale`, pending inputs,
removed/noncurrent actions, expired sources, and older input case versions mark
the affected display stale. Unknown/conflicting/unrequested/unavailable states,
missing or invalid timing, future observation/computation times, unsupported
freshness, and invalid/future input versions remain unknown. Unmarked legacy
records without timing/freshness remain unknown. A timestamp establishes record
observation timing, not verification of its contents; no arbitrary domain TTL
is invented. State and freshness are separate.

Record, parent-section, resource-search and directly referenced source signals
are combined conservatively: stale dominates unknown, then current. Referenced
`source_ids`, including capacity evidence references, must resolve to top-level
sources and are bounded to 24 per record. Unknown
status strings become `unknown`, not new display capabilities. Section retrieval
failure remains `unavailable` even if cached records are present. Domain notices,
source verification/provenance, seeded/sandbox labels, amounts, assumptions and
warnings remain in the snapshot and must be rendered alongside the metadata.

Confirmed resource availability requires the stored capacity wrapper's valid,
nonfuture `observed_at` and nonempty resolvable capacity `source_ids`. A bare
label, absent evidence, or invalid timing remains unknown; listing sources alone
cannot establish capacity. The snapshot itself is not changed. Stale capacity
evidence remains visibly stale, rather than being promoted to fresh capacity.
Current metadata never establishes household eligibility, receipt of aid or a
reservation. Incomplete finance results retain incomplete/unknown values.
Confirmed support, hypothetical scenarios, unreceived aid and actual money
remain their separate persisted records. An overdue schedule means condition
unknown; a dated last report does not establish present welfare. Requested
follow-up does not establish acknowledgment or active human response. Keep all
existing simulated-attempt labels and report/receipt times visible.

Version freshness is deliberately conservative. Existing plan/finance services
can save results calculated against the pre-commit version, and unrelated chat
state commits also advance the case version. Such records remain displayable
with stale metadata; this module does not rewrite their input version to claim
currency. A later dependency-aware invalidation contract is separate work. The
publication/turn commit itself must retain the validated input version, not
silently relabel it as the post-commit version.

## Exact integrator requirements

1. Review/freeze the additive schema with the shared contract/UI owners. No
   registered tool, agent flag, HTTP route or shared schema is supplied here.
   Use `PublishDashboardArguments` and `StructuredReplyArguments` as proposal
   schemas; do not expose internal prepared-envelope fields as model arguments.
   SDK/Pydantic structured output is only a proposal shaping layer; run these
   independent validators on raw arguments too.
2. Obtain the household snapshot and clock through trusted backend context.
   Serialize domain tool writes. Prepare outputs using a fresh read after the
   last accepted mutation; retrying against the original turn-start snapshot
   after tools write will cause a version conflict. Reject models attempting to
   supply case/session/channel/role/consent/time/version authority.
3. Add an internal CaseService publication/structured-turn commit path, not an
   unreviewed public command. Inside its transaction: reauthorize, check the
   active run/lease and deadline, resolve the stable parent/child event replay
   identity before version preconditions, read the current snapshot, call the
   appropriate `validate_*` function with the transaction clock, and commit
   only validated fields with the usual atomic version/audit update. A changed
   case version requires a fresh proposal/preparation or visible conflict.
   Preparation alone must never update a case or claim success.
4. Keep event IDs backend-derived and stable across retries. Fingerprint the
   accepted logical component/answer payload; reject reuse with different
   intent. Prepared timestamps are transport metadata, not a new logical event.
   Replay returns the accepted outcome without duplicate writes or a new model
   run. Rollback or publication rejection retains existing valid descriptors
   and assistant history. If components and a reply are meant to be one result,
   validate both against the same current version and commit them atomically;
   otherwise refresh before the second commit.
5. Store descriptor data only in `components` and the proposed metadata
   projection; store reply `text` and optional `questions` on the backend-owned
   assistant turn. Never copy arbitrary prepared-envelope fields into a case.
   Preserve the current `queued/running/complete/failed` lifecycle and failure
   issue handling. Streaming fragments are provisional text, not validated
   publications or usable final choice controls.
6. Resolve any incoming choice ID against the complete assistant turn visible
   to this household and its exact question/choices. Require pending answer
   correlation, reject stale/dangling selections, and resolve replay through
   the existing conversation event. A choice is a user conversation answer,
   never a command, consent grant, agency result or financial update. Even a
   label saying "Yes" cannot enroll check-ins/share location. Explicit consent
   and state transitions remain in their authenticated services/controls.
7. The fixed frontend renderer maps these ten kinds to implemented views and
   fixed controls. Unknown kinds get a visible unsupported result; they never
   load code. Always display relevant domain notices, stale/unknown metadata,
   availability, sources, mode labels and incomplete forecast assumptions.
   Plain assistant prose is not proof of an action or calculation: grounding
   and false-claim checks remain agent/runtime acceptance work. This module
   bounds prose and excludes executable structure; it cannot verify natural
   language truth or perform domain computation.
8. Before enabling wiring, add CaseService tests for authorized publication,
   cross-household denial, active-run expiry, version races after tool writes,
   rollback, restart/replay and conflicting event payloads; SDK tests for raw
   schema rejection and structured replies; and UI tests for empty/partial,
   failure/stale, skipped/multiple-choice answers and safe rendering. Real
   provider smoke remains user-run with private configuration/credential chain.

## Verification evidence

`python3 -W error::ResourceWarning -m unittest tests.test_outputs -v` exercises
51 output-specific tests pass. The earlier output + case/intake/access run passed
80 checks before the final capacity-evidence test and concurrent shared finance
schema tightening. The latest broader run discovers 81 checks: 79 pass and two
existing case/intake checks error with a null rejected snapshot:

```sh
python3 -W error::ResourceWarning -m unittest \
  tests.test_outputs tests.test_case_service tests.test_intake tests.test_access -q
```

Those two checks are
`CaseServiceTests.test_correction_retains_completed_work_and_marks_old_results_pending`
and `IntakeTests.test_partial_updates_preserve_prior_facts_needs_and_completed_work`.
Their legacy `baseline: {input_case_version: ...}` fixtures no longer match the
concurrently introduced shared `C08ForecastProjection` definition. Direct
validation reports `$.finance.baseline: Value does not match an allowed shape.`
This slice neither edits that shared schema nor changes those tests. The
independent output run still passes all 51 checks against empty/partial and
synthetic domain snapshots; full populated fixtures are output-domain fixtures,
not assertions of readiness for the concurrently evolving domain schemas.
Shared finance compatibility belongs to the integrator/domain owner.

Coverage includes dangling/cross-kind/ambiguous references, unsupported kinds,
malicious text/extra authority fields, bounded collections/text/nesting/bytes,
nonfinite/cyclic input, deterministic ordering, unknown capacity, stale/future
computed inputs, source expiry at commit time, incomplete finance, check-in and
review separation, old empty/partial snapshots, existing descriptor/turn shape
compatibility, purity and detached outputs. Domain modules remain unfinished
independently; fixed synthetic snapshots establish no live-provider evidence.
No private environment files, AWS credentials or secrets were read or loaded.
