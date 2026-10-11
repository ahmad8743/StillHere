# C06 bounded application-preparation handoff

Date: October 11, 2026. Proposed contract version: `0.1`.

**Domain slice: READY_FOR_INTEGRATION. Full C06: IN_PROGRESS.** This package is
implemented and verified with synthetic inputs. CaseService/command integration,
agent registration, shared-contract review, dashboard integration and live-provider
verification are separate, unfinished gates. No live model, agency lookup,
submission or contact was performed. Shared readiness/progress files were not
edited by this slice.

## Owned artifacts and boundaries

- `backend/stillhere/applications/`: pure preparation, validation and transition functions.
- `tests/test_applications.py`: 44 application-specific checks.
- `contracts/parallel/applications.schema.json`: proposed definitions, referencing
  the existing published rule, source, fact, ID and instant definitions.
- This handoff: assembly steps and remaining gates.

No CaseService, commands, shared schema, server, agent, README or progress edits
are part of this work. Concurrent planner, finance and other work is preserved.
The package has no storage, network, environment loading, provider, planner or
agent dependency. It uses C01's existing primitive validation and C04's published
rule-result validation; it never instantiates the rule store or retrieves a page.

## Pure Python boundary

```python
from backend.stillhere.applications import prepare_application, update_application

prepared = prepare_application(
    authorized_snapshot, prepare_arguments, published_rule_result,
    prepared_at=server_now, agency_receipts=trusted_receipts,
)
proposed = update_application(
    authorized_snapshot, update_arguments, published_rule_result,
    event_id=stable_child_event_id,
    occurred_at=user_observation_time, received_at=server_now,
    agency_receipts=trusted_receipts,
)
```

Both functions return independent JSON-shaped proposals, without mutating any
input. Same inputs yield the same result. Invalid shape, provenance, time, state
transition or reference raises C01 `InvalidInput` with a field and bounded message.
There is no hidden clock, generated ID, durable `applied` result or replay store.
CaseService supplies every timestamp, event identity and authorized input.

`prepare_application` returns `ApplicationPreparationResult`: `contract_version`,
`input_case_version`, `application`, public rule `sources`,
`household_eligibility: "unknown"`, and `external_submission: false`.
`update_application` returns `ApplicationUpdateResult`: the same boundary fields,
`event_id`, proposed `application`, proposed entire evidence metadata list,
`changed_evidence_ids`, and `requires_plan_reassessment`. It does not return or
modify facts, plan, money, consent, agency policy or the complete case snapshot.
`validate(name, value)` checks the proposed shapes; it supplements semantic checks
and does not establish authority.

### Caller-supplied authorized projection

`AuthorizedApplicationSnapshot` requires:

| Input | Meaning |
| --- | --- |
| `contract_version`, `case_id`, `case_version` | C01-issued identity/version; IDs confer no access |
| `facts` | Existing `{value, state, observed_at, source_ids}` wrappers; include explicit `document_issuing_state` and necessary Boolean rule fields |
| `evidence` | Proposed metadata-only `EvidenceRecord` entries with `id`, `requirement_key`, availability `state`, `provenance`, `observed_at`, `source_ids` |
| `plan.actions` | SelectedAction projection: `id`, `program_id`, `rule_id`, `rule_version`, `path_id`, `status`, `is_current`, `input_freshness` |
| `applications` | Accepted proposed `ApplicationRecord` objects, initially empty |
| `sources` | Source records with unique IDs; fact/evidence and trusted-receipt references must resolve here |

A full case snapshot is accepted by the Python functions; they project these
fields and the listed action fields before validation. The JSON Schema input
uses the small projection explicitly. Plan actions lacking program references
are irrelevant and excluded. A selected action must include the fields above;
C01 must construct this projection for legacy actions rather than guess a
program/path from their titles. The package imports no planner code and accepts
synthetic action projections with no evaluator, action dependencies, cost
extensions or task-history implementation.

Evidence `requirement_key` binds an availability report to one published proof
requirement. It does not assert that a document meets agency requirements.
Known available/missing records require user-reported or source-supported
provenance; source-supported records require known source IDs. Unknown,
conflicting and stale states preserve those labels. Only existing metadata
records can be changed in this slice. New evidence-record creation/normalization
must first be agreed and performed through C01's durable boundary; raw document
contents, uploads, numbers and arbitrary evidence fields are rejected.

Published rules are supplied in the existing `ProgramRuleResult` shape. They
must match the explicit issuing jurisdiction, input case version, operation time,
program and exact selected version/path. Their published graph, references,
official destination, review interval and source freshness are validated.
Current or damaged residence cannot substitute for the issuing jurisdiction.
Preparation and draft regeneration require `state: "available"` and current
reviews. Unknown, conflicting, stale, no-match or failed lookup raises an error
without changing prior records. **This slice therefore cannot accept a status
update while its published reference is unavailable or stale.** A follow-on C01
integration must agree a report-only, pending-preparation path if offline/status
acceptance during rule failure is needed; do not silently treat stale guidance
as current or suppress a user's unsaved report.

### Draft semantics

The output preserves every published node, AND/OR operator, child reference,
expected Boolean, timing, source reference and individual evidence reference.
`before_start`, `during_application`, and `before_receipt` remain distinct.
Later evidence is visible in the checklist and call script but does not alone
block review/start preparation. Satisfied OR alternatives suppress unnecessary
blockers/questions while all branches remain inspectable.

Draft answers are bounded **Boolean availability answers** (`"Yes"`, `"No"`, or
`""`) to the published requirements. They are not a complete agency form or a
mapping to unspecified form fields. Missing, non-Boolean, unknown, conflicting,
stale or future facts/evidence leave the answer blank. Conflicting evidence
retains all relevant record IDs. Observation time and user/source provenance
remain attached; source attribution alone is not household verification.
Evidence-kind requirements read typed evidence metadata, not a same-named
untyped fact. Action prerequisites and authority-confirmation requirements
remain blank; neither a completed task nor a public rule citation establishes
an agency action, applicability or eligibility.

Every draft remains provisional because the current published rules have
incomplete coverage. Call scripts are deterministic source-attributed questions
for the household to use; they do not place calls or contain arbitrary user
message bodies. Identity-detail availability can be recorded, but actual full
identity numbers and raw identity documents never become draft answers.
Any actual identity entry belongs at the official service. No eligibility,
approval, receipt, fee, deadline or amount is inferred.

## Tool-facing definitions

The schema's two argument definitions have object roots for future provider
compatibility; they do not accept authorization, case IDs, agency receipts, URLs,
source bodies, free-text correspondence or provider credentials.

```json
{
  "application_id": "application_synthetic_1",
  "action_id": "action_synthetic_1",
  "program_id": "co_state_id_replacement",
  "rule_version": "2026-10-10.1",
  "path_id": "co_id_online_renewal"
}
```

That is `PrepareApplicationArguments`. The case must already contain the
matching current action. `application_id` must be unused. C01 should allocate it
stably from the operation/event, or validate a supplied unused scoped record ID.
Preparation creates a proposed application with **no stage report**; generating
a draft does not mean the household completed a task or sent an application.

```json
{
  "application_id": "application_synthetic_1",
  "stage_change": {"stage": "submitted", "corrects_event_id": null},
  "correspondence": {
    "id": "correspondence_synthetic_1",
    "kind": "receipt_notice",
    "evidence_ids": ["evidence_synthetic_1"]
  },
  "evidence_changes": [
    {"evidence_id": "evidence_synthetic_1", "state": "available"}
  ]
}
```

That is the proposed `UpdateApplicationArguments` / `application.update` payload.
It requires at least one stage change, correspondence record or nonempty evidence
change list; all three may be combined in one atomic proposal. All references
must belong to this application/case/path. Correspondence IDs and per-event
evidence IDs must be unique. An evidence update always derives user provenance
and removes superseded source support. Related drafts regenerate immediately;
`requires_plan_reassessment: true` tells C01 that affected recovery outputs and
other applications sharing that evidence must be invalidated/reassessed.

### User reports, corrections and next steps

Stages: `draft`, `ready_to_submit`, `submitted`, `under_review`, `needs_evidence`,
`approved`, `denied`, `withdrawn`. These describe explicit **user reports**, never
verified agency actions. A first report can skip unobserved intermediate stages;
normal updates can advance ranks, move between under-review/evidence-request
states, and resubmit from `needs_evidence`. A backward move, a change from a
terminal report, or an older observed stage requires `corrects_event_id` naming
the active stage report. A correction can change any reported stage and retains
the old event in history. A stale/unknown correction ID is rejected.

Correspondence kinds: `receipt_notice`, `evidence_request`, `decision_notice`,
`other`. They are metadata-only, append-only household reports; no body, raw
attachment, identity values or inferred outcome is accepted. Occurrence time is
separate from receipt time, and correspondence sorts by observation time/ID.
No correspondence kind automatically changes either stage field.

History retains stage reports/correction references, correspondence IDs and
changed evidence states with event/observation/receipt times. C01's prior-case
audit must retain the full before/after evidence metadata. Duplicate accepted
events must be resolved by CaseService before invoking the pure transition;
this function rejects replay already visible in application history. History is
bounded at 64 events and correspondence at 32 records. Capacity fails explicitly
instead of truncating prior reports/corrections.

Next steps carry a typed `kind`, message, node/evidence/source references and
`basis` (`preparation`, `user_reported`, `agency_supported`). They distinguish
clarifying conflicts, gathering missing starting evidence, confirming unknown
requirements, reviewing the draft, checking reported status, reviewing reported
correspondence, reviewing verified decisions and clarifying disagreeing stages.
Evidence changes can revise the next step after a reported submission. Agency
requests remain separately supported; no next step sends anything externally.

### Caller-only agency outcomes

`agency_receipts` is an internal parameter, **never part of household/model tool
arguments**. Default is empty, yielding `agency_outcome: null`. No live agency
adapter is supplied. An `AgencyReceipt` requires `id`, `case_id`,
`application_id`, `program_id`, `stage`, `observed_at`, `verified_at`, `source_ids`.
Its stages are `received`, `under_review`, `needs_evidence`, `approved`, `denied`,
`withdrawn`. Receipt/verification times must be ordered and no later than the
operation. Its sources must be in the authorized case projection, with:

```json
{
  "id": "agency_source_synthetic_1",
  "issuer": "Colorado Department of Revenue, Division of Motor Vehicles",
  "verification_state": "agency_record_verified",
  "data_mode": "cached",
  "scope": {
    "case_id": "case_synthetic_1",
    "application_id": "application_synthetic_1",
    "program_id": "co_state_id_replacement"
  }
}
```

The caller supplies the ordinary source URL/timing/freshness fields separately
as applicable; C06 uses the identity/issuer/verification/mode/scope metadata
above, never raw correspondence. The issuer must match the published rule;
mode must be `live` or `cached`. Public `ProgramRuleSource` records, seeded/
sandbox sources, unrelated household records and user notices cannot satisfy
this boundary. **These labels are validation requirements, not a mechanism for
establishing trust.** C01 must obtain them through a reviewed trusted verifier;
never allow the model or an `application.update` payload to manufacture them.
This new private-source verification/scope vocabulary is proposed and requires
review; it is not part of an existing provider implementation.

The newest observed receipt is selected deterministically. Differing official
stages at the same latest observation time fail for caller reconciliation.
Every update must supply/revalidate the previously stored receipt as well as any
new one; a user correction cannot erase it. User and agency stages are stored
separately, and disagreement yields `clarify_stage` with both records retained.
Even a supplied verified approval leaves computed household eligibility unknown
and creates no accessible money, aid receipt or financial event. The public-rule
sources returned by the function supplement already-scoped agency source IDs;
private agency sources are not copied into the public catalog or rule output.

## Precise integration steps for the assembly owner

1. Review the proposed definitions with P1/P2. Adopt approved application,
   evidence, private-receipt and argument/result definitions into the shared
   schema/version process, then wire validators. Until then the shared public
   command remains unimplemented; this schema is a proposal beside the baseline.
2. Implement the authorized C01 prepare commit path and `application.update`
   handler. Authorize first; resolve event fingerprints/replay next; check the
   expected case version/run lease/deadline; read a consistent scoped snapshot.
   Allocate stable application/correspondence identities and project only
   necessary Boolean facts/evidence/actions/sources. Do not pass full identity
   numbers, document bodies or raw source text.
3. Select the existing C04 exact published version/path at server operation time.
   Supply this result and the authorized projection to the pure function. For
   agency outcomes, require separately provisioned trusted verification and
   household scope; use empty receipts until that gate exists.
4. Validate the returned schema **and recompute/compare the domain result** from
   the transaction's inputs. Check every application/action/node/evidence/source
   reference; source attribution may resolve in the existing case or the returned
   public sources. Recheck snapshot version and active run/deadline before commit.
5. Atomically replace only the matching application, changed evidence metadata
   and approved source projection; increment the case version once and retain
   C01 before/after audit/event result. Preparation's derived-result commit uses
   the same event identity rules. Do not persist the whole input snapshot from
   C06 or overwrite unrelated concurrent application/evidence entries.
6. If evidence changed, invalidate/reassess affected plan actions and other drafts
   sharing it. Preserve completed/skipped work. Any finance revision must go
   through C08; application approval never records a deposit or balance.
   Rule/fact corrections must likewise mark affected preparation pending until
   regenerated against a current source version. Rule-version migrations need an
   explicit reviewed re-preparation path preserving reports/history.
7. Map `InvalidInput` to the existing C01 rejected/clarification/conflict/unavailable
   envelopes by cause. Return visible unsaved/pending state for stale references
   or failed rule lookup. Keep the prior durable case intact on failure; do not
   classify provider failure as no-match or submission failure.
8. Add opt-in C02 adapters after commit handlers exist. The backend supplies
   session/case/version, stable turn/child-event IDs, times, published rules and
   trusted receipts. Model arguments use only the two object schemas above.
   Register prepare as read-only unless its commit path is explicitly enabled;
   update is a serialized mutation through C01. Provider schema compatibility,
   cancellation/deadline, replay, stale-version and household-isolation tests are
   required before registration. Limit results to a reviewed compact projection.
9. Render C10 checklist timing/OR branches, blank answers, observation/source
   provenance, official destination, separate reported/agency stages and typed
   next steps. Keep external submission and calls household-initiated. Offline
   UI changes retain original event/observation time and remain visibly unsent
   until C01 acknowledges them.

## Verification and remaining gates

Credential-free checks performed:

```sh
python3 -m unittest tests.test_applications tests.test_program_rules -q
```

**72 checks pass: 44 C06 checks plus 28 existing published-rule checks.** Tests
cover missing/conflicting/future/stale evidence and facts, exact Boolean/false
predicates, shared DAG and AND/OR alternatives, timing, provenance, invalid
references/graphs, current rule scope/version/time, input/output independence,
combined-update atomicity, report-only approval/correspondence, stage corrections,
old observations, replay/capacity, verified-receipt scope/conflicts and public-page
outcome forgery. Tests use synthetic facts/actions/receipts and the public reviewed
catalog. No private environment file, credential chain or live SDK is loaded.
An independent installed `jsonschema` Draft 2020-12 check passes the proposed
schema and preparation/update result examples with local reference resolution.

Remaining gates:

- Shared schema review/freeze; C01 authorization, atomic commit, event replay,
  version/run conflicts, rollback and full audit verification.
- C02 opt-in adapters/provider schemas and user-run live model/tool/reply/replay
  proof; no live-provider readiness is claimed here.
- C10 rendering, explicit user corrections and offline unsent/replay behavior.
- Trusted agency-record acquisition/verification, correction/retraction lifecycle
  and private-source policy; synthetic verifier labels prove only domain behavior.
- Evidence metadata creation/normalization; correspondence correction/retraction;
  report-only updates while rules are stale/unavailable; rule-version migrations.
- Reviewed non-Boolean agency-form field mappings and wider official instruction
  coverage, as separate slices. This domain does not invent missing form fields,
  proof alternatives, eligibility or complete national policy coverage.
