# StillHere — Component Contracts and Progress

Updated: October 11, 2026. Contract version: `0.1`. Build timebox: 12 hours.

Status: P1's C01 case/access component remains `IN_PROGRESS` for remaining domain handlers and operator provisioning. Its household/intake foundation and C01-facing Strands adapters are ready for integration. **C02's bounded first slice and C03 incident adapters/tool are `READY_FOR_INTEGRATION`.** The default live Bedrock proof passed with user-selected Claude Sonnet 4.5; all three C03 public source requests passed with synthetic geography. The broader C02 component remains `IN_PROGRESS` for later tools/output contracts. **P2's C08 finance and C09 intake/chat prototypes are `IN_PROGRESS` in `frontend/`.** Their initial fixture/mock boundary and four finance examples pass bounded offline checks; UI/backend integration and remaining acceptance behavior are pending. **C04's five bounded MVP slices are READY_FOR_INTEGRATION: reviewed referrals, scoped rule graphs, official-source fetching, separate candidate/discrepancy submission and local manual version publication.** The C04 milestone passed 203 non-HTTP checks, including 17 real-SDK checks, among 208 discovered checks. Current C05 and shared-checkout evidence is recorded below; the five existing HTTP checks still require an unrestricted local run. The required successful live-fetch example now passes: national USAGov retrieval plus the strict model/reply/replay proof are verified. Prior rule/referral live proofs pass. The new knowledge smoke passes its live source-failure/discrepancy/reply/replay branch at 13.569 seconds; national backend fetching is verified; Colorado live candidate extraction remains unverified. Full policy coverage, household eligibility and shared boundary review remain pending. **C05 is IN_PROGRESS with read-only evaluation, CaseService plan revision and task-report/reassessment slices READY_FOR_INTEGRATION; live planner/workflow proofs remain pending.** Other unimplemented domains, the contract freeze, and deployment remain pending. C09 implementation is outside this chat's current work. See the [agent handoff](agent-integration.md), [C03 handoff](incident-integration.md), [C04 referral handoff](resource-integration.md), and [C04 rules handoff](program-rules-integration.md), and [C04 fetch/review handoff](knowledge-review-integration.md).

The [project specification](project-specification.md) controls product scope. This document controls component boundaries, input/output contracts, ownership, and progress reporting. C01 now selects Python 3.11+, SQLite, a local standard-library HTTP adapter, and server-issued anonymous household bearer sessions. The confirmed direction is Strands Agents SDK with AWS Bedrock, with all application runtime/data hosted on Akamai Cloud. The user selected Claude Sonnet 4.5 for the current local slice and previously confirmed `us-east-2`; the working model/profile ID stays in private configuration. Akamai services remain pending; [infrastructure direction](infrastructure-direction.md) records the reference and credential gates. The JSON-shaped contracts below apply regardless of those choices.

## 1. Ownership and working boundaries

`P1` and `P2` identify ownership roles; they are not names of agents already dispatched.

| Owner | Owns | Integration boundary |
| --- | --- | --- |
| P1 — Agent and recovery infrastructure | Original packages A/B: Strands/Bedrock, validated tools, private persistence/access, sources, knowledge, prerequisite planning, application preparation, check-in engine, backend integration/deployment | Owns every durable case write and the backend command handlers. Calls P2's finance module with ordinary data. |
| P2 — User experience and finance | Original packages C/D: finance module, intake/chat UI, dashboard, check-in/location controls, operator queue UI, offline client behavior, text simulator, printable summary | Builds against a mock case/command service. Supplies a backend-compatible finance module without direct database, agent, or provider dependencies. |

P1 owns shared contract definitions and backend assembly. P2 owns shared synthetic fixture content and the acceptance walkthrough. Both review interface changes. Use separate implementation directories for these modules; concrete paths are recorded here at build start. Each owner can work independently against the agreed fixtures.

Build-start paths: P1 case service `backend/stillhere/`; shared executable definitions `contracts/case-service.schema.json`; P1 verification `tests/`; setup and HTTP handoff [README](../README.md). P2 prototype paths are `frontend/index.html`, `app.js`, and `styles.css`; initial fixtures/mock service are `frontend/fixtures.js` and `mock-service.js`; the browser finance engine is `frontend/finance-engine.js`. C01 defines its implemented requests/results and the full top-level snapshot shape; populated domain schemas and the two-owner freeze remain pending. P2 evidence below comes from its implementation and separately recorded synthetic checks.

Three interfaces cross the ownership boundary:

1. **Case snapshot:** P1 supplies one authorized read model; P2 renders it.
2. **User commands:** P2 submits structured intent; P1 validates, applies, and returns the updated state.
3. **Finance module:** P1 supplies financial state/events and feasible action costs; P2 returns validated updates and deterministic forecasts.

## 2. Shared data rules

| Rule | Contract |
| --- | --- |
| Version | All boundary requests/results carry `contract_version: "0.1"`. Freeze executable definitions together during hour 1. |
| IDs | Opaque strings for cases, events, records, actions, sources, schedules, and follow-up requests. IDs identify records; authorization comes from the authenticated session. |
| Time | Instants use RFC 3339 UTC strings. Calendar dates use `YYYY-MM-DD`. A case has an explicit IANA `time_zone`; forecast dates and selected contact times use that zone. Preserve reported/observed time separately from server receipt time. |
| Money | USD integer cents. Unknown amount is `null`, never zero. Negative forecast positions describe projected gaps; they are not actual cash balances. |
| Unknown facts | A fact is `{value, state, observed_at, source_ids}`. `state` is `unknown`, `user_reported`, `source_supported`, `conflicting`, or `stale`. Unknown value is `null`; conflicting alternatives remain available for clarification. |
| Sources | Each source has `id`, `url`, `issuer`, `scope`, `retrieved_at`, nullable `updated_at`/`expires_at`, `verification_state`, `freshness`, and `data_mode`. Freshness is `current`, `stale`, or `unknown`; data mode is `live`, `cached`, `seeded`, or `sandbox`. |
| Availability | Resource capacity/access is `confirmed_available`, `confirmed_unavailable`, or `unknown`, with supporting time/source. Directory presence alone leaves availability unknown. |
| Retrieval | Source operations distinguish `available`, `no_match`, `unavailable`, and `not_requested`. Cached/seeded data can accompany failure, but remain labeled and do not turn failure into `no_match`. |
| Collections | Empty arrays mean no records in the returned scope. Associated state/notices distinguish not yet retrieved from a completed search with no match. |
| Authorization | Household scope and operator scope are enforced by P1. Clients/model text cannot grant themselves roles or access by setting payload fields. |
| Consent | Check-in enrollment and shared-location permission require explicit user controls. Chat can propose enrollment; model inference cannot grant consent. |

## 3. Interface I — Case snapshot

### Operations

| Operation | Input | Output |
| --- | --- | --- |
| Create case | Authorized/anonymous scoped session; stable `event_id`; optional intake selections | New case ID, access association, and `CaseSnapshot`. Skipped facts remain unknown. Retry of the same creation event within that session resumes the same case. |
| Read/resume case | Session and `case_id` | Latest authorized `CaseSnapshot`, or a scoped access/unavailable error. |

P1 returns complete top-level snapshot sections even when their records are empty. P2 does not need the database layout, raw provider responses, graph storage format, or model transcript internals.

### Snapshot fields

| Field | Required contents |
| --- | --- |
| Identity/version | `contract_version`, `case_id`, monotonic `case_version`, `updated_at`, `time_zone`, `household_mode` (`synthetic` for the demonstration) |
| `facts` | Fact wrappers for intake, household, mobility, connectivity, and relevant constraints. Current place, damaged residence, and issuing jurisdiction remain distinct. |
| `needs` | IDs, kind, reported urgency, covered/uncovered/unknown state, and relevant source/fact references |
| `evidence` | IDs, document/proof kind, issuing scope, available/missing/unknown state, accepted alternatives, source references |
| `resources` | Retrieval state, normalized resource items, source references, and notices |
| `plan` | State/version, actions, blockers, pending questions, and reasons for revisions |
| `applications` | Program/official link, user-reported or provider-supported stage, missing evidence, draft content, and next action |
| `finance` | Financial ledger, scenarios, baseline/result state, source input case version, and calculation time |
| `check_in` | Enrollment, schedule/status, due time/grace, contact preference, last explicit report, simulated attempts, and pause/cancel state |
| `shared_location` | `null` or consented place/coordinates, observation time, source/accuracy, sharing purpose and allowed access. Not automatically copied from damaged residence. |
| `follow_ups` | Requests with trigger, status, consent scope, acknowledged owner, simulated attempts, outcome, and next action |
| `conversation` | UI-safe turns with IDs, role, text/choices, time, and turn state (`queued`, `running`, `complete`, `failed`) |
| `components` | Ordered allowlisted dashboard descriptors referencing records already present in the snapshot |
| `sources`, `notices` | Attribution and typed warnings/failures/uncertainties that can be displayed without parsing assistant prose |
| Optional `incident_context` | C03 `current`/`damaged` contexts with query/input version, provider states, bounded records, source times/IDs and notices; retain stale records after relevant case-input corrections |

An action has `id`, `title`, `purpose`, `status`, `execution_mode`, `requirements`, `costs`, nullable `deadline`, `source_ids`, `reason`, and alternative/blocker references. Action status is `ready`, `blocked`, `waiting`, `completed`, or `skipped`. A plan can also be `provisional` when facts or rules remain unresolved.

Dashboard descriptor kinds are `urgent_resource`, `next_step`, `task_list`, `blocker_controls`, `evidence_checklist`, `aid_tracker`, `finance_overview`, `scenario_comparison`, `check_in`, and `source_details`. Descriptors contain an ID, kind, referenced record IDs, and display order. P1 validates descriptors; P2 renders known kinds and reports unsupported kinds. Model-generated executable code is never a component payload.

### Minimal empty-case example

This is a complete top-level snapshot shape; populated record details follow the tables above. A mock can use it immediately and add records as fixtures are built.

```json
{
  "contract_version": "0.1",
  "case_id": "case_demo_001",
  "case_version": 1,
  "updated_at": "2026-10-10T15:00:00Z",
  "time_zone": "America/Chicago",
  "household_mode": "synthetic",
  "facts": {},
  "needs": [],
  "evidence": [],
  "resources": {"state": "not_requested", "items": [], "notices": []},
  "plan": {"state": "not_requested", "version": 0, "actions": [], "blockers": [], "questions": []},
  "applications": [],
  "finance": {
    "state": "not_calculated",
    "ledger": {"money_sources": [], "actual_events": [], "expense_commitments": [], "aid": [], "support": []},
    "scenarios": [],
    "baseline": null,
    "input_case_version": 1,
    "computed_at": null
  },
  "check_in": {"enrolled": false, "status": "not_enrolled", "schedule": null, "last_report": null, "attempts": []},
  "shared_location": null,
  "follow_ups": [],
  "conversation": {"turns": []},
  "components": [],
  "sources": [],
  "notices": []
}
```

## 4. Interface II — User commands and results

### Command envelope

All chat, dashboard, text-simulator, and operator changes use the same command service. The backend derives identity/role from the session; `channel` describes the interaction, not its authority.

```json
{
  "contract_version": "0.1",
  "case_id": "case_demo_001",
  "event_id": "event_demo_expense_001",
  "expected_case_version": 4,
  "occurred_at": "2026-10-10T15:05:00Z",
  "channel": "dashboard",
  "type": "finance.update",
  "payload": {
    "operation": "record_expense",
    "record_id": "expense_demo_001",
    "money_source_id": "cash_demo_001",
    "amount_cents": 1200,
    "expense_date": "2026-10-10",
    "category": "food",
    "commitment_id": "food_day_001"
  }
}
```

Channel values: `chat`, `dashboard`, `text_simulator`, `operator`, `system`. Only P1's authorized internal services may use `system`; only a scoped operator may submit operator commands. The example records a synthetic $12 food expense against a matching planned commitment; reconciliation updates that commitment rather than counting both outflows in full.

### Supported command types

| Type | Payload / required intent | Resulting effect |
| --- | --- | --- |
| `intake.submit` | Optional selections for help urgency, crisis type, needs, household group, and location | Partial facts and needs; initial questions/resources when enough context exists |
| `conversation.message` | `message_id`, text, optional choice ID | Persisted user turn; agent turn state and validated case changes. Ambiguous financial statements yield clarification/proposed entries. |
| `fact.correct` | Fact key, corrected value, relevant observation time | Auditable fact correction; affected plan/finance outputs invalidated or recomputed |
| `task.update` | Action ID; completed/skipped status or inability reason | Updated action; inability invokes relevant reassessment without destroying completed work |
| `finance.update` | Operation and typed financial record/event | P2 module validates/reconciles; P1 commits the result and refreshes forecasts |
| `scenario.set` | Scenario ID, label, dated hypothetical receipts/support or alternative action IDs | Editable scenario; no change to actual accessible money |
| `application.update` | Application ID, reported stage/correspondence, evidence changes | User-reported status and revised next step; no external submission |
| `help.request` | Reported need/message and optional related occurrence ID | Immediate official help directions and a simulated review request, including when check-ins are not enrolled |
| `check_in.enroll` | Explicit opt-in; due time, time zone, grace minutes, simulated channel preference | New schedule/occurrence and recorded consent |
| `check_in.reply` | Schedule/occurrence ID, reply (`okay_for_now`, `need_help`, `check_later`); new due time for `check_later` | Timestamped report; reschedule or immediate simulated review request where appropriate |
| `check_in.pause` | Pause/stop intent | Cancels future pending scheduled attempts; an already open review remains visible for acknowledgment/outcome |
| `location.share` | Explicit sharing permission, entered place or one-time fix, observation time, optional accuracy | New last-shared location under the permitted case-handler scope |
| `location.clear` | Stop sharing/remove shared location intent | Removes the active shared-location projection and access; does not erase unrelated damaged-residence facts |
| `follow_up.acknowledge` | Follow-up request ID | Assigns the authenticated demo operator and records acknowledgment |
| `follow_up.record` | Request ID; simulated attempt or outcome, unresolved needs, next action/due time | Auditable operator workflow update; cannot activate real contact/dispatch |

Finance operations cover money-source/balance changes, actual spending/receipts/transfers, expense commitments, aid/support changes, and auditable corrections. P2 defines executable record schemas using section 5 before both owners freeze the contract. Local edits may be pending; they do not masquerade as accepted server changes.

### Result envelope and error behavior

Every result includes `contract_version`, `event_id`, `status`, server `received_at`, nullable `applied_case_version`, `case_snapshot` (nullable), and `issues` (array). `applied_case_version` identifies the original accepted mutation even when the returned snapshot is newer. An issue has `code`, `message`, optional `field`, and `retryable`. Status values:

| Status | Meaning / client behavior |
| --- | --- |
| `applied` | Durable command accepted; show the returned version. An accepted chat message may still have an agent turn running. |
| `already_applied` | Same logical event was previously accepted; return its original outcome and latest authorized snapshot without repeating effects. |
| `needs_clarification` | Relevant domain mutation is unapplied; show field-specific questions/proposed data. A chat turn may already be saved. |
| `conflict` | Expected version is stale; return the latest authorized snapshot. Reconcile before resubmitting. |
| `rejected` | Invalid input, unsupported version/type, or insufficient access. No requested mutation is applied; access failures return no private snapshot. |
| `unavailable` | Required service failed; retain prior valid case data and show the reason. Retry the same event ID after a lost response. |

Idempotency key is `(case_id, event_id)`; authorize before looking up any result, then resolve duplicates before checking the expected version. A duplicate logical payload never applies twice. Reusing an ID with a different logical payload is rejected. Transport preconditions such as `expected_case_version` may change on a retry that has not yet applied; a correction to the requested facts/amounts is a new logical event with a new ID.

P1 checks versions and commits validated changes atomically. A conflict does not silently overwrite a newer fact. A lost response is resolved by retrying/reading the event result; it does not prove the event failed. Chat-derived tools use the same validation, access, and version rules as direct controls. Their durable effects receive stable child-event IDs so replaying a turn cannot duplicate spending or schedules.

### C01 executable slice and transport

The local service implements `POST /v1/sessions`, `POST /v1/cases`, `GET /v1/cases/{case_id}`, and `POST /v1/commands` for `fact.correct`, `intake.submit`, `conversation.message`, and `task.update`. A session request carries only `contract_version`; the server chooses household authority. Case creation takes `contract_version`, stable `event_id`, and explicit IANA `time_zone`, plus optional `intake: IntakeSelections` and `occurred_at`. Omitted intake still creates the original empty snapshot. Reads require `X-Contract-Version: 0.1`; private routes require a bearer session. Operator/system channels are rejected until trusted scoped services exist.

`FactCorrectionPayload` is `{fact_key, value, observed_at}`. The server derives `user_reported` (or `unknown` for `null`) and never accepts client-supplied provenance. Domain-specific facts remain ordinary JSON data; they do not grant consent/access or modify money. The command fingerprint excludes only `expected_case_version`. A valid conflicting event reserves that identity, so a retry may change the precondition but requires a new ID for changed intent. Malformed transport or an unusable event ID returns a versioned `AccessError`; valid case/command submissions use the existing result envelope.

`IntakeSelections` has optional `help_urgency`, `crisis_type`, `needs`, `household_group`, and `current_location` fields. Its exact enum values, nullable/empty choices, and mutually exclusive selections are defined in the shared JSON Schema and [README](../README.md#typed-intake-for-the-ui-and-agent). The same shape is creation's `intake` or the entire `intake.submit` payload. Command `occurred_at` is the intake observation time; creation uses optional `occurred_at` or receipt time. Missing fields preserve prior answers; explicit uncertainty produces unknown facts. Selected needs get stable `IntakeNeed` IDs, unknown coverage, and fact references. Unselected needs remain present; no household headcount, balance, location-sharing permission, or enrollment is inferred. Intake remains skippable and partial.

Creation plus intake commits at version 1; each accepted later intake increments the case version once. `backend/stillhere/commands.py` contains the deterministic handlers/schema mapping; the service retains every durable write and cross-cutting access/replay/version rule. New audit events retain the prior whole case; an additive migration preserves first-slice SQLite databases and historical prior-fact audits without inventing historical snapshots.

Corrections and intake preserve completed work and conservatively invalidate existing plan/finance outputs with `state: "pending"`. Additive optional `pending_input_case_version` records the new target version while retained finance `input_case_version` identifies the old calculation. Recalculation/replanning remain future handlers. Full payloads, HTTP statuses, setup, and retry rules are recorded in the [handoff README](../README.md). The case service persists intake and conversation; C02 now supplies plain-text replies and validated C01 tools. Urgent referrals/resources, remaining domain integration, operator access, frontend/backend wiring, and the full contract freeze remain pending.

An agent/model failure after a user turn is stored marks that turn failed and keeps previously valid data. If a calculation/replan is pending, its section exposes `pending` and the input version; an old forecast is never presented as current for newer inputs.

### C02 first slice and tool extensions — ready for integration

The bounded C02 slice is implemented with Strands Agents SDK `1.59.0`, an explicitly configured AWS Bedrock model, durable chat-turn handling, and the default `read_case` / `correct_fact` tools. The existing C01 intake service also has a tested `submit_intake` adapter behind an opt-in flag. These adapters and the bounded runtime are `READY_FOR_INTEGRATION`. The confirmed default-path user-run smoke records two tool calls and `smoke_passed` at 6.072 seconds, verifying the saved fact, reply, and unchanged replay version; the user identifies the current working model as Claude Sonnet 4.5. A later user-run log passes at 18.681 seconds with one tool call; its mode is omitted from the log. Safe logs omit model IDs, so model attribution comes from the user's report. The real SDK loop also passes with a scripted model transport. The broader C02 component remains `IN_PROGRESS`: detailed resource/rule retrieval, planning, finance, check-in, structured output, and memory belong to later slices. C04 now supplies independent opt-in referral and read-only reviewed-rule tools. [Setup, state/replay rules, and verification](agent-integration.md).

Strands runs inside the application backend on Akamai. Bedrock is the external inference provider; AWS model access does not change case ownership, session authority, command envelopes, or the P2 API. The SDK is pinned and the implementation requires explicit Bedrock model and region settings. Keep both providers' credentials server-side. Akamai deployment is a separate bounded slice after the local model/tool path works.

Keep agent configuration/turn orchestration separate from tool adapters and domain handlers. A central allowlist registers each tool's name, description, argument schema, result schema, and callable. New tools add their own adapter, contract definitions and focused checks without changing the agent loop. Domain logic stays behind the existing case service or the owning module's interface; adapters do not write directly to SQLite.

Authenticated session/case context is injected by the backend, never accepted as model-selected authority. Writes retain the command envelope, version conflicts, and stable child-event identity across replay; a changed logical mutation requires a new event ID. Each new tool must verify its schema, scoped access, relevant failure behavior, and any durable replay effect before registration. Shared contract changes follow the existing version/review protocol.

The [planned tool inventory and Strands feature mapping](strands-capabilities.md#planned-tool-inventory) covers later tools, their owning components, and operations that remain outside the household agent's registry. C01 services and their C02 read/fact/intake adapters are implemented. C03 adds opt-in `get_incident_context`, with backend-supplied geography and an internal CaseService commit. C04 adds opt-in `find_resources` with a reviewed seeded catalog and internal CaseService commit, plus read-only `retrieve_program_rules` with explicit document-issuer scope, bounded `fetch_official_source`, and structured public `propose_rule_candidate`/`report_rule_discrepancy` submissions. Local manual publication is outside the household registry; other inventory tools remain unregistered until their services/schemas are ready.

### C03 incident context — ready for integration

`backend/stillhere/incidents/` implements bounded NWS active alerts, USGS radius/time catalog queries and OpenFEMA declaration/area/program context. Shared `IncidentGeography`, `IncidentQuery`, `IncidentSource`, `IncidentRecord` and `IncidentContext` definitions are additive under `0.1`. `IntakeLocation` accepts optional coordinates/state/county fields; place/postal-only intake remains valid, without automatic geocoding. Reported current and damaged locations stay separate. Missing geography, failed sources, successful empty queries, partial coverage and stale inputs have distinct states.

The opt-in Strands tool uses only scope and a 1–365 day lookback; case/session/run authority, geography and current time come from the backend. `CaseService.commit_agent_incident_context` validates and atomically commits context, attribution, case version and previous-case audit with active-run/version/input checks and one effect per parent/query. Relevant corrections retain old context as stale. This adds no public command type or household eligibility claim. See [C03 setup, provider limits, freshness and evidence](incident-integration.md).

The synthetic live proof recorded at `2026-10-11T01:12:25.900302Z` (October 10 locally) returned validated `no_match` from all three APIs. Populated normalization/failure evidence and the real SDK tool path use labeled fixtures. Full offline suite: 99 checks. A live Sonnet/C03-specific tool proof is available through `agent.smoke --env-file .env.local --incidents` and has not yet been run with credentials. C09 implementation does not gate this slice.

### C04 resources and reviewed knowledge — bounded MVP ready for integration

All five implementation slices are `READY_FOR_INTEGRATION`; live-provider proof
and integration gates are recorded separately:

| Slice | Implemented boundary | Verification |
| --- | --- | --- |
| Reviewed referrals | `resources/`, opt-in `find_resources`, national routes/Colorado 211 and CaseService atomic case projection | 24 focused checks; user-run live smoke passed at 18.535 seconds |
| Read-only published rules | `knowledge/rules.py`, opt-in `retrieve_program_rules`, explicit document issuer, scoped AND/OR graphs, active or exact archived version | 28 focused checks; user-run live smoke passed at 14.992 seconds for the replacement program |
| Bounded official fetch | `knowledge/official.py`, five approved public source IDs, unreviewed hashed receipts, bounded transport and honest failure fallback | Synthetic transport/SDK checks pass; user-run national USAGov fetch and strict model/reply/replay proof pass; Colorado live rule extraction remains pending |
| Separate candidates/discrepancies | Structured known keys/reasons and backend-selected public evidence; CaseService atomic public record/private replay link | Privacy, household isolation, deadline/version guards, duplicate effects, rollback and provider-failure/replay checks pass |
| Local manual review/publication | OS/database authority, candidate/catalog concurrency checks, graph/provenance validation, immutable versions and active catalog | Temporary-database approval/rejection/conflict/history/restart tests and the offline workflow pass; deployed operator provisioning remains C01 work |

`CaseService` owns all durable writes. Review records/catalogs and private effect
links occupy separate tables in the same protected SQLite file. Published lookup
never reads pending candidates; household/model tools cannot approve policy.
Review submission leaves household domains, case version/audit and published
rules unchanged. Manual publication is an explicit local administrator operation.
The shared `0.1` contract adds ten fetch/review definitions in this iteration,
reviewed `cached` rule/source modes and optional source content hashes; P2 review
and the full contract freeze remain pending.

Colorado is the chosen bounded reference jurisdiction. Referral smoke uses
synthetic Denver shelter/food/transport needs; knowledge smoke uses an explicit
Colorado document issuer. No named disaster or disaster type is asserted.
Catalog `2026-10-10.rules.2` preserves replacement program `2026-10-10.1` and its
original two sources. Separate `co_state_id_proof_options` adds partial standard
proof and exceptions graphs based on production documents/exceptions pages
reviewed at `2026-10-11T03:53:07Z`. Applicability requires official confirmation;
first-application requirements are not automatically applied to renewal.
Full proof lists, household eligibility, fees, policy effective dates and actual
service capacity remain unknown. `coverage_complete` stays false.

C04 completion evidence: 186 non-HTTP checks passed, including 34 fetch/review/workflow
checks and 16 real pinned-SDK checks. That full discovery ran 191 checks with the
same five host loopback-bind errors. The credential-free end-to-end fetch through
manual publication/restart/replay workflow passes. Earlier user-run rule/referral
proofs remain valid for their bounded paths. The user also reports the offline
knowledge workflow passed. The safe log confirms user-run `--knowledge` passed
at 13.569 seconds with two completed tool calls and `retrieval_state: unavailable`,
verifying real-model source-failure/fallback, unpublished discrepancy submission,
durable reply and replay. The log does not retain the source-failure reason.
The later national USAGov fetch and strict model proof pass (details below);
Colorado live candidate extraction remains unverified. No credential files were read,
no live Bedrock calls were made by Codex, Sonnet 4.5 is retained and C09 is untouched.
Usage was checked between milestones and remained above 20% remaining.

[Referrals](resource-integration.md), [rules](program-rules-integration.md), and
[fetch/review setup, scope and user checklist](knowledge-review-integration.md).
The required successful C04 live-fetch example is now verified. The user-run
credential-free USAGov receipt records `data_mode: live`, 1,524 characters,
no truncation, an actual guidance excerpt and content hash at
`2026-10-11T05:16:53.123600Z`. The strict Bedrock proof fetched again at
`2026-10-11T05:18:02.014708Z`; the safe log confirms one completed tool call,
completed run and `smoke_passed` at 13.265 seconds with `mode: fetch` and
`retrieval_state: available`. Its saved quoted/cited reply, unchanged
household domains/published rules and replay checks passed. This source remains
unreviewed national guidance and cannot enter Colorado rule submissions.

The user's DMV request still returns HTTP 403; Codex backend DNS failures remain
host-specific. Neither negates the independently successful national fetch.
Colorado live candidate extraction, local HTTP checks and shared boundary review
remain separate gates. Full discovery contains 208 checks; all 203 non-HTTP
checks pass, including 17 real-SDK checks and ten strict fetch-example checks.
C05 is now IN_PROGRESS. Its first read-only deterministic
`evaluate_recovery_options` slice is READY_FOR_INTEGRATION, with the boundary and
evidence below. The user's successful-fetch prerequisite is satisfied.

### C05 read-only prerequisite evaluation — first slice ready for integration

P1 implemented `backend/stillhere/planner/evaluator.py` and independently opt-in
`evaluate_recovery_options` through `STILLHERE_AGENT_ENABLE_PLANNER=true` (default
false). Full C05 is `IN_PROGRESS`; this read-only slice is
`READY_FOR_INTEGRATION`, with live Sonnet/planner verification still pending.

Nine additive `0.1` definitions cover scoped arguments/results, requirement
states, OR branches, blockers/questions, options and unknown cost inputs. The
backend selects the authorized case version, explicit document issuer, time and
published active/exact archived rules. Boolean availability/completion facts
match requirement keys; missing, unknown, stale, conflicting, malformed or future
answers remain unknown. Agency confirmation needs source-supported provenance.
Untyped evidence/tasks never supply guessed answers. AND/OR truth and necessary
blockers/questions are deterministic; every source-supported OR/sibling path
remains inspectable. Invalid/cyclic/dangling graphs cannot produce usable options.

In-person access checks `office_transport_available`; no car alone triggers a
question about other transport. Explicit unavailable transport blocks the office
path and preserves the published online alternative, whose `internet_access`
and other prerequisites remain separate. All current references are partial,
so matching all modeled answers still leaves an option provisional. Eligibility,
fees, transport amounts and dates remain unknown/null. No plan, task, audit,
case-version, policy or financial-domain write occurs through evaluation.
CaseService retains ordinary durable chat/replay ownership.

28 planner checks and two new real-SDK checks pass; focused planner/rule/SDK
validation passes 75 checks. The shared non-HTTP run passed 288 checks including
55 finance checks introduced by concurrent work. A later full discovery ran 295
checks: 290 passed, including 57 concurrent finance and 19 total real-SDK checks;
the same five HTTP checks failed only at host-prohibited loopback binding. The
C05 addition itself contributes 30 checks to the previous 208-check baseline.
Concurrent finance work was preserved and its component readiness is owned
separately. Tests used synthetic configuration, temporary cases and scripted
providers; no private configuration or credential files were loaded. Usage was
checked between milestones (36% of the five-hour allowance remained after code
validation). Sonnet 4.5 stays configured by the user; C09 is untouched.

[Planner contracts, semantics, unresolved gates and user-run checks](planner-integration.md).
The next milestone below completes validated plan revision/CaseService commit
and task history. Current remaining gates are typed evidence/action dependency
links, trusted confirmations and dated cost integration. P2 boundary review/full freeze and live `agent.smoke --planner`
remain separate gates; Colorado HTTP 403/live extraction is still unverified.

## 5. Interface III — Independent finance module

Owner: P2. Backend wrapper and durable commit: P1. No database, network, model, or framework dependency belongs inside the authoritative calculation/reconciliation module.

### Operations

| Operation | Input | Output |
| --- | --- | --- |
| `apply_financial_update` | Ledger snapshot; typed operation/event; event ID; effective/receipt time; reference to matching commitment/deposit when known | `applied`, `needs_clarification`, or `rejected`; proposed next ledger, changed record IDs, reconciliation notes, and issues. No persistence side effects. |
| `forecast_finances` | Ledger; `start_date`; case time zone; fixed 14-day horizon; up to three scenarios; dated costs for feasible action alternatives; input case version | Baseline, scenario results, action comparisons, assumptions/warnings, and source input version. Same inputs produce the same domain results. |

### Financial input records

| Record | Minimum fields / meaning |
| --- | --- |
| Money source/balance | ID, type (cash/account/received assistance), `balance_cents`, `as_of`, accessibility, restrictions and their evidence. Snapshot includes the financial event IDs already reflected in it. |
| Actual event | ID, kind (expense/receipt/transfer/correction), integer cents, effective time/date, money-source IDs, source, and matching commitment/aid/import references where known |
| Expense commitment | ID, category, dated amount, priority, essential flag, actual amount already fulfilled, action/source references; one-off date or daily recurrence with explicit end date |
| Aid | ID, application stage, amount/date if known, received/unreceived state, restrictions/evidence, and any matching actual receipt ID |
| Support | ID, confirmed/hypothetical state, covered expense/category IDs, date range, amount or quantity limit, actual consumption, and evidence |
| Scenario | ID, label, dated hypothetical changes, and selected alternative action IDs. Scenario assumptions never mutate the actual ledger. |
| Action alternative | Alternative/path ID and dated expense commitments from the planner. Unknown cost stays `null` and produces a warning. |

Stages, restrictions, and support eligibility come from entered/source-supported facts; the module cannot invent them. Opening balances include already reflected events. Unmatched/ambiguous reconciliation produces a clarification instead of a fabricated total.

Baseline excludes unreceived aid. Apply confirmed support, then compatible received restricted funds, then accessible unrestricted money. Cap overlapping support. Process each forecast date's included receipts before that date's expenses, using entered expense priority and stable IDs to break ties; expose this day-level assumption. Known timing that makes money unavailable until after an expense must be preserved, not treated as available earlier. Unknown balances/costs produce incomplete-result warnings.

### Forecast output

Each result contains `scenario_id` (`baseline` for the baseline), `input_case_version`, `start_date`, `end_date`, accessible opening cents (nullable if unknown), daily projections, nullable `first_gap`, ending projected position, assumptions, and warnings. A daily row contains its date, included receipt cents, support/restricted coverage, uncovered expense cents, projected position, and affected expense/action IDs. `first_gap` identifies the date, uncovered amount, and affected expenses. Actual current available money and a projected ending position are distinct values.

Synthetic expected-output excerpt for the specification's no-aid case:

```json
{
  "scenario_id": "baseline",
  "input_case_version": 4,
  "start_date": "2026-10-10",
  "end_date": "2026-10-23",
  "opening_accessible_cents": 30000,
  "first_gap": {"date": "2026-10-14", "amount_cents": 5500},
  "ending_projected_position_cents": -64000
}
```

This excerpt omits daily rows/assumptions for readability. The input is $300 opening cash, $65 daily essentials for 14 days, and a $30 day-1 cost. The other three required financial cases and their expected results are in [the financial demonstration](project-specification.md#financial-demonstration). P2's browser engine reproduces all four canonical gaps/ending positions and preserves the ledger during scenario comparison in a synthetic Node check. Its browser-specific interface/output still needs the full finance contract, validation/reconciliation behavior, and backend integration.

## 6. Internal component input/output contracts

These contracts keep P1's internal modules replaceable and let P2 produce fixtures without calling real providers. References to facts/records use the shared definitions above.

| ID / component | Owner | Input | Output |
| --- | --- | --- | --- |
| C01 — Case service/access | P1 | Authorized session; case ID; command/version/event envelope | Scoped snapshots, atomic event outcomes, version/history; no cross-household data |
| C02 — Strands/Bedrock orchestration and tools | P1 | User turn, current scoped case, allowed tools and their results | Persisted assistant turn, focused questions, validated structured tool commands/component descriptors; model/provider failure state |
| C03 — Incident adapters | P1 | Current/damaged geography, crisis type, time, provider configuration | Normalized alerts/events/declarations with applicability, sources, freshness and per-provider retrieval states |
| C04 — Resource catalog and reviewed knowledge | P1 | Needs, incident/jurisdiction, relevant facts, program IDs/version filters | Normalized resources and published rules; availability/unknowns; candidate discrepancies remain unpublished |
| C05 — Prerequisite/constraint planner | P1 | Relevant facts/evidence, published AND/OR rules, incident scope, prior actions, user priorities | Feasible/provisional actions, blocked prerequisites/cycles, alternatives, costs, reasons and preserved completed work |
| C06 — Application preparation | P1 | Official program instructions, case facts/evidence, chosen action | Official link, required-fact checklist, draft answers/script, blank unknowns, source references; no submission |
| C07 — Check-in engine | P1 | Explicit consent/commands, schedule, clock time, existing occurrences/reports/reviews | Updated schedule/report, deterministic due/overdue state, labeled simulated attempts, deduplicated review requests |
| C08 — Finance module | P2 | Financial inputs and costed alternatives from section 5 | Validated next ledger and reproducible forecasts/gaps/scenarios; clarification where required |
| C09 — Intake and chat UI | P2 | Initial/resumed snapshot, assistant text/choices, local selections/messages | Intake/chat commands; skipped/unknown answers and turn progress/failures rendered |
| C10 — Dashboard and direct controls | P2 | Allowed component descriptors and authorized snapshot | Rendered records, sources/uncertainty, task/fact/finance/application commands; no separate authoritative ledger |
| C11 — Check-in/location controls | P2 | User-scoped check-in and last-shared-location data | Explicit enrollment/reply/pause/share/clear commands; timestamps and unsent/overdue labels |
| C12 — Demo operator queue | P2 UI; P1 access/projection | Operator-authorized review projection and command outcomes | Queue, acknowledgment, simulated attempt/outcome commands, owner/next-action visibility |
| C13 — Offline cache/replay | P2 client; P1 command processing | Opt-in saved authorized snapshot, local events, connection state | Readable saved data, stable queued IDs, ordered replay, visible conflicts/unsent state, scoped local erase |
| C14 — Text-channel simulator | P2 | Numbered synthetic text input, same snapshots/command service | Same case changes plus concise plain-text contacts/addresses/actions/finances/check-ins, visibly simulated |
| C15 — Printable summary | P2 | User-selected snapshot records | Printable next steps, contacts, dates and source times; sensitive finance/location details excluded unless selected |
| C16 — Backend assembly/deployment and acceptance | P1; P2 walkthrough | All modules, environment configuration, fixtures, required acceptance cases | Runnable prototype, setup/source/fallback documentation, recorded verification evidence and demo |
| O01 — Plaid Sandbox adapter, optional | P2; P1 private integration | User-initiated sandbox connection and permitted test provider data | Normalized balance/transaction changes into C08; labeled sandbox timing/conflicts/disconnect; credentials never exposed to model/UI |

The planner emits costs as data; it does not invoke or depend on finance internals. P1 invokes C08 and supplies the comparison to orchestration. Finance can be built against fixture action costs while the planner is unfinished. UI and text channels share commands; neither writes the database independently.

### Check-in and operator details

Keep schedule state separate from reported welfare and review ownership. Schedule states are `not_enrolled`, `scheduled`, `due`, `reminder_attempted`, `overdue`, `answered`, `paused`, and `canceled`. Review states are `requested`, `assigned_acknowledged`, `contact_attempted`, and `outcome_recorded`. An `okay_for_now` or `need_help` reply marks the relevant occurrence answered; a future check-in needs an explicitly selected new time. `check_later` creates that new agreed occurrence. A reply does not silently close an already assigned review or unrelated unmet need.

An occurrence has a stable ID, due time, grace deadline, reminder-attempt ID, report/receipt times, and review reference. Advancing the demo clock past the grace deadline creates overdue/condition-unknown state and one review request. Processing the same occurrence repeatedly creates no duplicate contact/review events. An explicit help request can create review immediately and shows official urgent contacts regardless of schedule enrollment.

P1's operator projection exposes only consented context: case reference, relevant needs, last report/time, due/grace time, simulated attempts, permitted last-shared location with age, assignment and outcome/next action. It does not automatically expose the full household financial ledger. `assigned_acknowledged` requires a scoped operator's acceptance; queue insertion alone never implies active human response.

All welfare reminder/call events use `simulation: true`. No live field-response action exists in the MVP command set. A conversational live-SMS stretch does not enable live welfare outreach.

### Offline details

P2 keeps queued events in local order with original IDs/times and last known case version. After each accepted replay, use the returned case version for the next pending event. On conflict, read/reconcile; unrelated edits may be deliberately rebased, while conflicting facts/amounts require visible resolution. A changed logical payload gets a new event ID.

A local reply is `queued_local` until the backend accepts it. Preserve original report time and server receipt time; notify the existing reviewer of a late reply. A local pause/location-clear command also remains visibly pending until accepted. Clear household-scoped local data on the selected erase/logout action; do not replay one household's queue into another session. Offline forecasts show their original input version and pending changes.

## 7. Mock and fixture handoff

P2 implements a mock that supplies Interface I snapshots and Interface II results. P1 uses the same fixtures and fixed finance outputs while the real C08 module is unfinished. Replace mocks through adapters; rendering and domain code should not change. Fixture IDs/dates/source modes are stable and every seeded contact/resource is labeled demonstration data.

| Fixture | Required content | Verification target |
| --- | --- | --- |
| F01 — Partial household | Mother, two children, lost home/documents, unknown mobility; $300 cash after entry | Intake can skip facts; urgent guidance and evolving case remain usable |
| F02 — No car | F01 plus corrected mobility; source-backed remote/transport alternative or honest blocker | Affected plan/costs revise; completed work persists |
| F03 — Finance cases | Four synthetic schedules from the project specification; approved/unreceived and restricted aid variations | Exact gaps/positions, no double counting, uncertainty visible |
| F04 — Source failure/cycle | Unavailable provider, stale/unknown capacity, no matching declaration, circular document requirements | Distinct failure states and official fallback; no invented eligibility or capacity |
| F05 — Check-in | Enrolled schedule, controllable clock, overdue request, acknowledgment, reply/pause and optional stale location | No login-based escalation, no duplicate attempts, no claim of live response |
| F06 — Replay/conflict | Queued spending and late check-in, lost acknowledgment/retry, concurrent fact correction | One effect, preserved times, visible conflict/unsent state |
| F07 — Scope | Two synthetic cases and scoped user/operator sessions; malformed source/component input | Isolation and validation; no permission expansion |

Current fixture state: `frontend/fixtures.js` supplies the initial synthetic case/finance ledger, `frontend/mock-service.js` handles local reads/intake/corrections, and `frontend/finance-engine.js` supplies the four basic F03 calculations. A synthetic Node/Python check validates the initial snapshot and five mock results against the shared `0.1` definitions, covering intake, correction, replay, version conflict, and unsupported chat rejection. Four canonical finance examples pass a separate Node check without mutating the ledger. The full F01–F07 fixture set, restricted/unknown finance variations, reconciliation, and UI acceptance walkthrough remain pending. Browser chat uses separate demo state and is not connected to this mock command path or the HTTP API. These checks use an in-memory browser mock; interactive rendering and live frontend/backend integration remain unverified.

## 8. Component progress tracker

Update this table at handoffs and when a milestone changes. Report implementation state separately from evidence. Status vocabulary: `NOT_STARTED`, `IN_PROGRESS`, `READY_FOR_INTEGRATION`, `INTEGRATED`, `VERIFIED`, `BLOCKED`, or `DEFERRED`. Use `BLOCKED` only with a concrete failed dependency and next resolution action. A mock demonstration is not `VERIFIED` production behavior.

`VERIFIED` means the component's required MVP behavior has passed the recorded check, including its relevant failure path. It does not mean production-ready. Percentage estimates are unnecessary.

| ID / component | Owner | Build status | Evidence / implementation path | Next task or gate |
| --- | --- | --- | --- | --- |
| C01 Case/access | P1 | IN_PROGRESS | Case creation/read/resume, household access, replay/version/audit handling, four public handlers and internal C03 context/C04 resource/C05 plan commits implemented; C01-facing Strands adapters are READY_FOR_INTEGRATION; see `backend/stillhere/agent/` and [handoff](agent-integration.md) | Implement the remaining 11 public command handlers, other derived-result commit paths, and scoped operator provisioning; P2 review additive schemas before full component readiness |
| C02 Agent/tools | P1 | IN_PROGRESS | First slice READY_FOR_INTEGRATION: pinned Strands/Bedrock runtime, scoped tools, durable turns, limits and safe diagnostics; default live proof passes at 6.072 seconds with user-selected Sonnet 4.5; opt-in C03, C04 and all three C05 tools exercise the real SDK; current discovery has 330 checks: 325 non-HTTP passes here and all 330 passing in the user-run local suite | Integrate the three ready C05 slices; later evidence/dependency, output/finance/check-in/memory tools remain pending. Prior rule/resource live proofs pass; the `--knowledge` failure branch passes; national fetching passes the strict live proof; Colorado live candidate extraction remains pending. C09 is outside current work |
| C03 Incident adapters | P1 | READY_FOR_INTEGRATION | `backend/stillhere/incidents/`, typed schemas, opt-in `get_incident_context` and internal CaseService commit; live synthetic NWS/USGS/OpenFEMA requests all return validated `no_match`; 28 C03 offline checks plus real SDK coverage for populated/failure/replay/conflict/freshness paths; [handoff](incident-integration.md) | Optional user-run Sonnet/C03 proof; shared boundary review at contract freeze; all five bounded C04 slices are ready; three C05 slices are ready; typed evidence/dependency and cost integration are next |
| C04 Resources/knowledge | P1 | READY_FOR_INTEGRATION | All five bounded slices: reviewed referrals, scoped active/history rule graphs, approved official fetch, separate public candidate/discrepancy records and local manual immutable publication. 203 non-HTTP checks pass (34 fetch/review, 17 real SDK); offline end-to-end publication/restart/replay passes. Prior user-run rules/resources smokes and the new knowledge failure-branch smoke (13.569 seconds) pass; [fetch/review handoff](knowledge-review-integration.md) | USAGov `fetch_smoke` and strict user-run `--fetch` pass (13.265 seconds); C05 read-only evaluation ready; Colorado candidate extraction remains pending; five local HTTP checks; P2 boundary review. Broader policy coverage, service capacity and deployed operator access remain separate |
| C05 Planner | P1 | IN_PROGRESS | Three slices READY_FOR_INTEGRATION: evaluation, CaseService atomic revision and task reports/reassessment; `planner/`, three independent opt-in tools, typed owned actions/history and compact summaries. 108 focused checks and all 325 non-HTTP checks pass (21 SDK); [handoff](planner-integration.md) | Read-only Sonnet `--planner` and saved-plan/task `--plan` pass after schema fix; P2 review; typed evidence/action dependency links, trusted agency confirmations, priority/deadline ordering, completion corrections and dated cost integration remain separate |
| C06 Application prep | P1 | NOT_STARTED | None | Produce sourced checklist/draft with unknowns left blank and no external submission |
| C07 Check-in engine | P1 | NOT_STARTED | None | Demonstrate clock transitions, consent/pause, help request and deduplication |
| C08 Finance | P2 | IN_PROGRESS | `frontend/finance-engine.js`, `frontend/fixtures.js`, finance view in `frontend/index.html`/`app.js`; four canonical forecast gaps/positions and ledger-preserving scenario comparison pass a synthetic Node check | Implement shared finance input/output contracts and backend-compatible module; validate unknown/restricted inputs, updates and reconciliation; integrate through C01 |
| C09 Intake/chat | P2 | IN_PROGRESS | `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`; browser-local crisis-first flow and separate canned recovery/general/finance conversations; mock intake/correction results satisfy shared schemas, but UI chat/intake state is not connected to the mock command path/API | Integrate with C01/C02 snapshots and commands; render skipped/unknown answers and queued/running/complete/failed turns; verify correction, resume and failed-turn behavior; implementation remains deferred in this chat |
| C10 Dashboard/controls | P2 | NOT_STARTED | Finance panels/scenario selector exist under C08; the shared allowlisted-component renderer and authoritative case controls are unimplemented | Render allowed components; match chat/control case state and show unknowns |
| C11 Check-in/location UI | P2 | NOT_STARTED | Prototype notice-city selection/opt-in exists; check-in and consented last-shared-location command controls are unimplemented | Verify opt-in/reply/pause/share/clear and stale/unsent labels |
| C12 Operator queue | P2 + P1 access | NOT_STARTED | None | Acknowledge a synthetic review; record simulated attempt/outcome and scoped visibility |
| C13 Offline/replay | P2 + P1 processing | NOT_STARTED | None | Queue/replay stable events; verify conflict, late reply and local erase |
| C14 Text simulator | P2 | NOT_STARTED | None | Route numbered inputs through shared commands; output usable plain-text contacts |
| C15 Print summary | P2 | NOT_STARTED | None | Print selected steps/contacts/dates; verify sensitive fields are opt-in |
| C16 Assembly/acceptance | P1 + P2 walkthrough | NOT_STARTED | None | Integrate early path; document environment, checks and runnable demo |
| O01 Plaid Sandbox | P2 + P1 integration | DEFERRED | None | Attempt only after required core checks pass and sandbox access is ready |

Progress: C01's household/intake foundation and C01-facing Strands adapters are available for integration. C01 stays `IN_PROGRESS` because broader domain handlers and operator provisioning are unfinished. C02's bounded runtime and C03 incident adapters/tool are `READY_FOR_INTEGRATION`, with offline SDK checks and separate live Bedrock/default-tool and public-source evidence. C02 as a whole stays `IN_PROGRESS` for later tools/output contracts. All five bounded C04 slices are `READY_FOR_INTEGRATION`; national backend fetching and the strict live reply/replay proof pass, while Colorado live candidate extraction, local HTTP checks and P2 review remain pending. C05 is `IN_PROGRESS` with evaluation, CaseService revision and task-report slices `READY_FOR_INTEGRATION`; live planner/workflow proofs, deeper evidence/dependency and cost integration remain pending. Full policy coverage and household eligibility remain unknown. P2's C08/C09 browser prototypes and initial fixture/mock implementation are `IN_PROGRESS`; bounded finance/schema checks pass. Remaining domains, frontend/backend integration, populated schemas, the full fixture set, and the joint contract freeze remain pending. C09 implementation is deferred for this chat.

C01 is not complete at component level. C09 owns the P2 intake/chat user interface and is `IN_PROGRESS` following the pulled frontend prototype; its available backend prerequisites are recorded under C01/C02. C09 readiness requires contract-backed state and the rendering/interaction checks in its tracker row.

### Milestones and handoff gates

| Target | Required handoff | Current state |
| --- | --- | --- |
| Hour 1 | Both owners agree executable contract definitions; select stack; record module paths; P1 proves model tool calling; P2 establishes mock fixtures | IN_PROGRESS — backend/frontend paths and initial mock fixture established; live Bedrock tool proof passed; two-owner freeze and remaining shared fixtures pending |
| Hour 3 | Real intake → durable case → rendered dashboard path; return/resume works | IN_PROGRESS — intake persistence, resume and live agent/tool proof pass; UI/dashboard integration pending |
| Hour 5 | Source/planner path and independent finance module available; frontend runs against fixtures | IN_PROGRESS — C03 source adapters ready; frontend finance uses an initial fixture and passes four basic forecast checks; three bounded planner slices ready; deeper planning, complete finance module and integrated source/plan UI pending |
| Hour 8 | Finance and check-in/queue integrated; adaptive family journey and offline/text/print basics work | NOT_STARTED |
| Hours 8–10 | Required scenarios pass; relevant source/model failures, household isolation, duplicate processing and conflicts verified | NOT_STARTED |
| Hour 12 | Runnable demonstration, setup/source/fallback documentation and recorded evidence complete | NOT_STARTED |

The local Bedrock credential/model path and pinned SDK/tool compatibility have passed the recorded bounded proof. C03's three public providers pass synthetic live requests returning `no_match`; populated/failure responses use offline fixtures. C04 public referral and Colorado DMV rule pages have been reviewed, and mode-labeled user-run rule/referral model proofs pass. All five bounded C04 implementation slices are ready; the new knowledge failure branch passes; national backend fetching/strict reply proof pass; Colorado live candidate extraction remains pending. Actual service-capacity checks remain separate. Other provider domains and Akamai deployment remain unverified. Partner agreements are later-pilot work, not an MVP blocker. Live SMS and Plaid must not hold up the required simulated/manual experience.

## 9. Change and progress protocol

Before parallel implementation, P1 records the executable schema/module locations; P2 records fixture/mock locations. Each owner uses the same definitions. An interface change updates this document and examples, informs the other owner, and updates the mock and real adapters together. Additive optional fields can stay within `0.1`; breaking field/type/semantic changes require a new contract version.

For every meaningful progress update, record component ID, owner, previous/new state, implementation path or commit, verification evidence, and next issue/action. Read the latest tracker before editing shared state. Only the owning role changes its component's build status; P1 records shared integration status after checking both sides.

| Date | Change | Evidence / next action |
| --- | --- | --- |
| 2026-10-10 | Created contract baseline and two-person tracker; all required components marked NOT_STARTED | Planning documents only; owners freeze executable contracts at build start |
| 2026-10-10 | P1 C01: NOT_STARTED → READY_FOR_INTEGRATION for the household create/resume/fact-correction slice | Python/SQLite implementation and shared JSON Schema; `python3 -W error::ResourceWarning -m unittest discover -s tests -v` passes 13 service/HTTP checks; P2 boundary review and additional domain handlers next |
| 2026-10-10 | P1 C01: READY_FOR_INTEGRATION retained; expanded with typed intake, shared command handlers and additive audit migration | `commands.py`, shared `IntakeSelections`/`IntakeNeed` definitions, `tests/test_intake.py` and HTTP checks; 26 checks pass; P2 uses the documented vocabulary and C02 model/tool proof is the next P1 slice |
| 2026-10-10 | P1 C02: uncommitted first attempt rolled back; NOT_STARTED under revised infrastructure direction | Retained committed C01 case/intake foundation at `0d56429`; all backend/schema/test files match that commit and all 26 tests pass after rollback. Strands SDK + AWS Bedrock replaces Qwen inference, entire app hosted on Akamai. Reference-only workshop clone excluded by `/.references/`; contract `0.1` unchanged. Next: implement the bounded Bedrock/tool slice and validate live access when credentials are ready |
| 2026-10-10 | P1 C01: READY_FOR_INTEGRATION → IN_PROGRESS after review of the planned tool inventory; C02 remains NOT_STARTED | C01 implements the case-read, fact-correction, and intake services used by planned tools, but remaining command handlers/derived-result commit paths and scoped operator provisioning are pending. Existing implementation and 26-check evidence are retained. [Strands inventory](strands-capabilities.md#planned-tool-inventory) documents 29 planned tools and covers all 15 command types; no Strands adapters were implemented. Next: bounded C02 model/tool proof, followed by agreed domain slices and C01 handlers |
| 2026-10-10 | P2 C08/C09: NOT_STARTED → IN_PROGRESS | Added the initial contract-shaped browser fixture and local adapter, the deterministic 14-day finance scenarios, and a partial crisis-first chat UI. No new checks were run; expected-value review, reconciliation, backend integration, and remaining C09 acceptance states are next |
| 2026-10-10 | P1 C02: NOT_STARTED → IN_PROGRESS; C01-facing adapters READY_FOR_INTEGRATION | `agent/` implements pinned Strands/Bedrock runtime, default read/fact tools and opt-in intake, durable turns/claims, stable child events, raw-schema hooks, ordered queue continuation and bounded execution. Additive conversation/tool schemas retain contract `0.1`. Full suite: 53 passing checks including six real-SDK scripted-model checks and HTTP chat; no live Bedrock invocation. Private `.env.local`, blank template, Git exclusion and Codex deny profile supplied. Next: user-configured live proof and P2 boundary review; remaining C01 domains/operator work unchanged |
| 2026-10-10 | P1 C02: IN_PROGRESS retained after smoke troubleshooting | `agent/config.py`, `agent/diagnostics.py`, `agent/smoke.py`, provider/runtime hooks and `service.py`: missing settings are named without values, empty shell fields no longer mask explicit local settings, owner timeouts retain `agent_timeout`, and smoke writes allowlisted phase/error-code logs. All 58 offline checks pass, including expired-run authority and log privacy checks. User reported `agent_not_configured` then `agent_interrupted`; no successful live proof yet. Next: user reruns GPT-6 Luna with a supported source region/profile and Codex reviews the safe log; no credentials are read by Codex |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; local SDK import timeout repaired | Safe smoke log stops at `sdk_import_started` until the 60-second timeout, before client setup or AWS inference. Installed `.venv` package files were cloud-offloaded (`dataless`). Reinstalled pinned dependencies in `~/Library/Caches/StillHere/agent-venv-20261010`, linked project `.venv` to that local environment, preserved `.venv.cloud-backup`, and ignored both in Git. Provider imports pass in 3.881 seconds; all 58 offline checks pass using the repaired `.venv/bin/python`. Next: user reruns the live smoke command; AWS account/model access remains unverified |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; generated/wrapped AWS error diagnostics repaired | Latest user-run safe log completes SDK import/client setup and fails during model invocation in under one second; its prior generic `Exception` entry does not establish the cause. `agent/diagnostics.py` now recognizes AWS `ClientError` subclasses and bounded cause/context chains without retaining messages, notes or request state. All 60 offline checks pass, including generated/wrapped access-denied fixtures and the real SDK failure path. Next: user reruns smoke and Codex inspects the newly retained AWS code; no successful live proof or account-access conclusion yet |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; AWS invocation denial identified | Latest safe user-run log completes SDK import at 1.618 seconds and client setup at 1.788 seconds, then records `ClientError` / `AccessDeniedException` at model invocation (2.521 seconds). This resolves the prior unknown provider-failure code; it does not distinguish IAM permissions, activation/payment requirements or account-level access, and does not prove a Free plan restriction. Handoff records AWS console/access checks. Next: resolve AWS access before rerunning the live tool/update/reply proof; no new code or test changes |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; validation failure captured and safe reason diagnostics added | Latest user-run log records `ValidationException` at 0.712 seconds, before a tool call; the old log lacks its detailed message. `agent/diagnostics.py` now maps fixed AWS phrases to allowlisted reasons without retaining message text or values. Real-SDK mocked Converse transport validates the actual request against Botocore and verifies only `maxTokens`, two non-strict tools and no extra model request fields. All 62 offline checks pass. Next: user supplies the non-secret AWS validation message or reruns smoke to capture a safe reason; server-side model compatibility, account access and successful live proof remain unverified |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; inference-profile requirement identified | Two new user-run safe logs record `ValidationException` with `reason: "inference_profile_required"` at 0.744 and 0.735 seconds. AWS rejects direct on-demand invocation. User confirmed switching to bare Claude Haiku 4.5. Handoff supplies its supported `us.anthropic.claude-haiku-4-5-20251001-v1:0` / `us-east-2` process override, preserving credentials in the user's private configuration. The model ID came from chat; no credential files or secret values were read. Next: user runs with the supported inference profile; successful live proof remains pending. Documentation-only change; prior 62 offline checks remain the code evidence |
| 2026-10-10 | P1 C02: IN_PROGRESS retained; live model/tool step reached before resource failure | Latest safe user-run log records `tool_call_complete` at 1.922 seconds, then `ResourceNotFoundException` at 2.054 seconds. This establishes a model-returned tool request, not successful fact/update/reply proof. Older diagnostics did not classify the resource failure. Safe reasons now recognize missing Anthropic use-case details and `FTUFormNotFilled`; smoke also prints sanitized current-run code/reason. All 63 offline checks pass, including a real-SDK resource failure after a saved fact effect. Next: user checks Anthropic first-time-use/agreement state and reruns with safe reason diagnostics; the actual cause and successful live proof remain pending |
| 2026-10-10 | P1 C02 first slice: IN_PROGRESS → READY_FOR_INTEGRATION; full C02 remains IN_PROGRESS | User-run safe logs record two complete tool/update/reply/replay proofs: `smoke_passed` at 2.291 seconds and latest at 6.072 seconds. The user confirmed Claude Sonnet 4.5 as the current working model; safe logs omit model IDs and private configuration was not read. `agent/access.py`, smoke access mode and fake-client privacy checks add optional read-only account/form/agreement diagnostics. Full offline suite: 70 checks. Next: P2 reviews/integrates C09 against the existing API; agent work proceeds to C03/C04 retrieval and later domain tools. C01 handlers/operator provisioning, broader C02 output/tools and Akamai deployment remain pending |
| 2026-10-10 | P1 C03: NOT_STARTED → READY_FOR_INTEGRATION; C09 work deferred for this chat | `incidents/`, shared C03 definitions, CaseService internal commit, stale-input invalidation and opt-in agent tool implemented. Live synthetic Denver queries return validated `no_match` from NWS, USGS and OpenFEMA; report `var/incident-smoke.json` is ignored. Full offline suite: 99 checks (28 C03 and 10 real-SDK checks); populated/failure, expiry, relevance, scope, replay, conflict, deadline and rollback evidence is synthetic. SDK optional defaults fixed by validating original tool input. New user-run `agent.smoke --incidents` verifies Sonnet/C03 when run; no new source credentials or credential-file reads. Next: C04 resource/reviewed-knowledge slice; broader C01/C02 and deployment remain pending |
| 2026-10-10 | Agent/C03 milestone verification recorded | Latest user-run safe phase log records one completed tool call, completed model/run phases, and `smoke_passed` at 18.681 seconds. The log omits mode/model identity, so this entry records an agent smoke pass without assigning it to the default or incident mode. C03 remains READY_FOR_INTEGRATION; next agent/tool slice is C04, with C09 deferred |
| 2026-10-10 | Shared milestone synchronized with P2 frontend commit `a140b99`; C08/C09 remain IN_PROGRESS | Preserved P2 implementation and both progress histories after pull. Corrected stale frontend/mock/fixture status. The combined backend suite passes all 99 checks. All four canonical finance examples and ledger immutability pass; the initial snapshot and five mock command results satisfy `0.1` schemas with intake/correction/replay/conflict checks. JavaScript syntax checks pass. Browser rendering, full finance behavior, UI/API integration and joint freeze remain pending; C09 implementation remains outside this chat |
| 2026-10-10 | P1 C04: NOT_STARTED → IN_PROGRESS; bounded referral slice READY_FOR_INTEGRATION | `resources/`, reviewed public catalog, additive shared schemas, opt-in `find_resources`, CaseService atomic commit, stale corrections and user-run `agent.smoke --resources` implemented. Colorado/synthetic Denver selected; four nationwide routes and Colorado 211 contact reviewed at `2026-10-11T01:59:58Z` (October 10 locally), all seeded with unknown availability/requirements/eligibility. 24 C04 checks plus real-SDK resource coverage pass; 119 non-HTTP checks pass. Full 124-check discovery has five baseline loopback-bind errors under host policy, including the requested-access rerun; HTTP verification remains pending. Sonnet 4.5 retained, C09 untouched, no credential reads/live model calls. Next: versioned reviewed rules and alternatives; live model/C04 proof is user-run; full C04, broader C01/C02, joint freeze and deployment remain pending |
| 2026-10-10 | Agent smoke verification recorded | Latest safe user-run log records one tool call, completed run and `smoke_passed` at 20.356 seconds. The older log omits mode/model identity, so C04-specific live evidence cannot be assigned. New smoke logs now record an allowlisted mode. Sonnet 4.5 remains the user-selected model; no credentials were read |
| 2026-10-10 | P1 C04: IN_PROGRESS retained; read-only reviewed-rule slice READY_FOR_INTEGRATION | `knowledge/`, nine additive definitions, opt-in `retrieve_program_rules`, explicit document-issuer scope and two partial Colorado state-ID renewal paths implemented. Production DMV pages reviewed at `2026-10-11T02:24:54Z`; complete online eligibility, proof alternatives, fees and policy effective dates remain unknown. 28 focused rule checks, 13 total real-SDK checks and 149 non-HTTP checks pass; full 154-check discovery retains five host loopback-bind errors. Exact-query/deadline/concurrency guards and read-only domain/audit checks pass. Added user-run `--rules` smoke and safe mode metadata; no credential reads/live Bedrock calls, Sonnet 4.5 retained, C09 untouched. Usage checked between milestones and stayed above 20% remaining. Next: user live rule proof, then deeper document alternatives/bounded official fetch and separate candidate/manual review contracts; full C04 remains pending |

| 2026-10-10 | P1 C04: IN_PROGRESS retained; both implemented slices gain live-provider/tool verification | The safe user-run log confirms `--rules` at 14.992 seconds and `--resources` at 18.535 seconds, each with one completed tool call, a completed run and mode-labeled `smoke_passed`. These verify the bounded live model/tool/reply/replay paths, not full C04, household eligibility or live resource capacity. No credential files were read; Sonnet 4.5 and C09 boundaries retained. Offline evidence stays at 149 non-HTTP checks; five HTTP checks remain unverified by Codex under host loopback policy, and a user-run full unit-suite outcome has not been separately reported. Next: bounded `fetch_official_source`, then separate candidate/discrepancy/manual review contracts and deeper rules; C05 planning follows |

This file is a manually maintained handoff record. It does not run a monitor, dispatch agents, or automatically inspect another person's progress.

| 2026-10-10 | P1 C04: IN_PROGRESS → READY_FOR_INTEGRATION for bounded MVP | Completed official fetch, separate candidate/discrepancy submission and local manual review/version publication; deeper scoped proof/exception graphs remain explicitly partial. CaseService owns atomic writes; household tools cannot publish. Ten new shared definitions plus cached source/rule modes/hash attribution remain subject to P2 review. 186 non-HTTP checks pass, including 34 knowledge and 16 real-SDK checks; full 191-check discovery has five existing loopback-bind errors. Disposable offline publication/restart/replay passes. Direct backend public GET fails DNS here; new user-run `--knowledge` proof distinguishes available/unavailable retrieval. Previous rules/resources live passes retained. Sonnet 4.5 retained, C09 untouched, no credential reads or live Bedrock calls; usage remained above 20%. Next: user checks/shared review and C05 planner |

| 2026-10-10 | C04 user-run offline and live failure-path verification recorded | User terminal confirms the credential-free knowledge workflow passed. Safe `var/agent-smoke.jsonl` confirms `mode: knowledge`, two completed tool calls, completed run and `smoke_passed` at 13.569 seconds with `retrieval_state: unavailable`. This verifies real Bedrock source-failure/fallback, unpublished discrepancy submission, unchanged policy/household domains, durable reply and replay. Source-failure reason is absent from the safe log; the prior Codex-host DNS failure cannot establish the cause of this user run. Successful live fetching/candidate extraction and unrestricted local HTTP checks remain pending. No credential files read; no tests rerun for this documentation-only update |

| 2026-10-10 | C04 public-source failure diagnosis added | Added credential-free `knowledge.check_source` using the existing approved public transport. Safe JSON reports fixed DNS/TLS/timeout/connection categories, HTTP status and extraction counts; no model calls, environment loading, page bodies, URLs, exception text or durable case writes. Standard and requested-access Codex probes both return DNS failure; that cannot establish the cause of the earlier user-run smoke. Six new diagnostic checks plus knowledge/agent regressions pass (66 focused checks); discovery contains 197 tests. Previous complete-suite evidence remains 186 passes/five blocked HTTP checks among 191. User can reproduce the request in their terminal without another Bedrock invocation; successful live extraction remains pending |

| 2026-10-10 | C04 user source-access reproduction recorded; C05 next slice scoped | User `knowledge.check_source` output reports `source_http_error`, HTTP 403 and `http_error` in 0.435 seconds. This establishes server refusal for that request, distinct from Codex-host DNS failures; the server policy and earlier smoke historical cause remain unknown. Successful live extraction stays pending. Next recommended chunk: read-only deterministic C05 graph evaluation and opt-in `evaluate_recovery_options`, using existing published seed and retaining unknowns; plan commits/revision and task updates follow separately. No C05 code started; documentation-only update |

| 2026-10-10 | C04 successful live-fetch example prioritized before C05 | User requires a working new-information fetch before moving on. Added exact approved USAGov lost-ID source (national scope, no seeded fallback, no Colorado review evidence), widening only fetch arguments/receipts and keeping host/path/redirect limits. Web reader successfully retrieves useful public guidance; Codex backend requests still fail DNS. New credential-free `knowledge.fetch_smoke` and strict user-run `agent.smoke --fetch` require live useful text, provenance and (Sonnet) quoted/cited saved reply, unchanged domains/policy and replay; failure handling cannot pass. 67 focused and all 203 non-HTTP checks pass, including ten new example and 17 real-SDK checks; discovery contains 208 tests. Five existing HTTP checks and actual local/backend/live-model success remain pending. Usage stayed above 20% remaining. Sonnet 4.5 kept, no credential reads or live Bedrock calls, C09 untouched; C05 remains NOT_STARTED |

| 2026-10-11 | C04 required successful live-fetch example verified; C05 prerequisite satisfied | User-run `knowledge.fetch_smoke` returns available/live, 1,524 characters, no truncation, public guidance and a content hash at `2026-10-11T05:16:53.123600Z`. User-run `agent.smoke --fetch` fetches again at `2026-10-11T05:18:02.014708Z`; safe log confirms one completed tool call, completed run and `smoke_passed` at 13.265 seconds with `mode: fetch` and available retrieval. Fresh useful public text, quoted/cited saved reply, unchanged domains/policy and replay passed. Source remains unreviewed national guidance; Colorado DMV still returns 403 and live Colorado candidate extraction remains pending. Build status stays READY_FOR_INTEGRATION, with shared review/local HTTP gates separate. Documentation-only update; no credential reads or tests rerun. C05 is NOT_STARTED and next |

| 2026-10-11 | P1 C05: NOT_STARTED → IN_PROGRESS; first read-only slice READY_FOR_INTEGRATION | Added pure bounded AND/OR evaluation, independent opt-in `evaluate_recovery_options`, nine additive result definitions and user-run `--planner` proof. Required blockers/questions respect OR alternatives; explicit Boolean facts retain unknown/provenance; agency gates stay unverified without trusted support; no-car access/online alternative and null costs remain honest. CaseService owns durable turns; no plan/task/domain/audit/policy writes. 28 planner plus two new real-SDK checks pass, 75 focused checks pass; full shared discovery later ran 295 checks with 290 passes (including 57 concurrent finance checks) and five existing loopback-bind errors. Prior work/concurrent finance preserved; Sonnet 4.5 retained, C09 untouched, synthetic configuration only; usage checked between milestones. Next: user live planner proof/P2 boundary review, then typed evidence/action links, plan revision/commit and task history; Colorado extraction stays unverified |

| 2026-10-11 | P1 C05: IN_PROGRESS retained; saved-plan and task-report slices READY_FOR_INTEGRATION | `planner/service.py` recomputes published requirements inside the authorized CaseService transaction and atomically commits plan/source/version/audit with lease/deadline/replay/rollback checks. `task.update` and opt-in `update_task` record completion/skipping/inability/resolution with separate occurrence/receipt times, immediately reassess the affected route, retain completed/skipped/removed work and never infer facts, agency approval or money. Independent `revise_recovery_plan`/task flags and compact summaries keep model context bounded; per-action freshness prevents unrelated-program refresh. Seven additive schemas and `--plan` proof remain subject to P2 review. 31 lifecycle plus two new SDK checks pass; 108 focused and all 325 non-HTTP checks pass among 330 discovered (21 SDK, 59 finance). Five HTTP checks remain host-blocked/pending; no live credentialed proof was run. Prior work/Sonnet 4.5/C09 preserved; usage checked from 25% down through 20%, 15%, 11% and 7% remaining. Next: user live proofs/P2 boundary review; deeper evidence/dependency links, trusted confirmations, priority/deadline and cost integration |


| 2026-10-11 | C05 verification evidence updated | User reports all 330 local checks passing with ResourceWarning promoted to an error, satisfying the five HTTP checks blocked here. The safe log records a passing read-only `--planner` proof. The saved-plan/task `--plan` attempt fails at the first model request with `ValidationException` / `unclassified`, before any tool completion; the rejected parameter is not identified by the sanitized log. Saved-plan/task live verification remains pending. The RuntimeError/ClientError lines in the passing suite are intentional provider-failure fixtures. No credential files read, no model change, no live call by Codex; documentation only |


| 2026-10-11 | C05 live-failure investigation and schema compatibility fix | Failing `--plan` stops before tools; new `update_task` alone exposes a root `anyOf`, matching Anthropic's documented tool-schema rejection. Changed only its provider-facing envelope to an object, preserving strict backend union validation and raw-input checks. Extended mocked outgoing Converse validation to all four plan-mode tools and retained rejection of missing/conflicting task fields; added fixed-phrase safe diagnostic classification. All 325 non-HTTP checks pass after the fix. Prior user-run 330 checks passed before this fix; post-fix full local suite and live `--plan` rerun remain user gates. Root-schema cause is probable, not live confirmed. Sonnet 4.5, private config and C09 untouched; usage began at 3% remaining |


| 2026-10-11 | C05 bounded live plan workflow verified | Safe log records two user-run `mode: plan` successes (12.444 and 13.516 seconds), each with three completed tools, after the schema fix. Smoke validates two saved revisions, retained user-reported online completion, blocked office route, source attribution, unknown costs/eligibility, provisional plan, sourced saved reply, unchanged domains/policy and replay without duplicate writes. Three slices remain READY_FOR_INTEGRATION and full C05 IN_PROGRESS; synthetic proof does not verify agency outcomes or live Colorado extraction. No private config read; docs only; usage 1% remaining |
