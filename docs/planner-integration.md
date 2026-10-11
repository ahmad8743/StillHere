# C05 recovery evaluation, saved plans and task reports

Updated October 11, 2026. **Three bounded slices are READY_FOR_INTEGRATION:
read-only evaluation, CaseService plan revision, and task reports/reassessment.
Full C05 is IN_PROGRESS.** Deterministic AND/OR evaluation,
scoped opt-in tooling and synthetic SDK/replay evidence pass. Live Sonnet/planner
verification and P2 boundary review remain pending. Keep the user's Sonnet 4.5
configuration. CaseService owns all durable writes; C09 is outside this work.

## Enable and call

`STILLHERE_AGENT_ENABLE_PLANNER=true` independently adds
`evaluate_recovery_options`; the flag defaults to false. It initializes the
published rule store without registering `retrieve_program_rules` or enabling
any other optional group. The default read/fact tools remain enabled.

```json
{"program_id":"co_state_id_replacement","version":"2026-10-10.1"}
```

`version` is optional. `co_state_id_proof_options` separately evaluates the
published proof/exception paths. Scope comes from the authorized case's explicit
`document_issuing_state`, with the same active/exact archived lookup and time
rules as C04. Current/damaged location cannot establish document issuer.
Case/session identity, facts, costs, graphs, URLs, role and time are never tool
arguments. Pending candidates and unreviewed fetch receipts never enter evaluation.

## Household inputs

This bounded slice reads `snapshot.facts[requirement.key]` as an exact Boolean
availability/completion predicate. Use the existing `fact.correct` command to
record explicit answers. For example, `credential_lost: true`,
`prior_credential_details_available: false`, or `email_access: true` are reports
about the named condition. Credential numbers, SSNs and document contents are
unnecessary. A requirement's published `evidence_state: unknown` remains unchanged;
household evaluation is returned separately.

| Input | Evaluation |
| --- | --- |
| Missing key, unknown/null value | Unknown; ask the corresponding question |
| Stale/conflicting fact | Unknown; retain its state and request clarification |
| String, number or object in a Boolean predicate | Unknown; no coercion |
| Missing observation time or observation after query time | Unknown; unusable observation |
| Boolean `user_reported` or `source_supported` fact | Compare exactly with the published Boolean expectation; retain provenance |
| `authority_confirmation` requirement | Requires `source_supported` plus a supporting source ID from that requirement's reviewed attribution; an ordinary household report stays unverified |

The public fact command cannot assert source-supported provenance. A later trusted
confirmation workflow is still needed for these agency gates; this slice leaves
them unanswered in ordinary household use. An assertion of eligibility in chat
never supplies that authority. Even a supported modeled confirmation does not
establish complete household eligibility under this partial catalog.

Evidence/task records do not yet have agreed typed satisfaction/link contracts.
The evaluator does not guess matches from document descriptions, completed task
titles, intake needs or resource listings. A Boolean action predicate describes
explicitly reported completion; it does not create or complete a saved task.
Completed work and prior plan records remain intact.

## AND/OR behavior and result

AND is unmet when any child is unmet, unknown when no child is unmet and any is
unknown, and satisfied when all children are satisfied. OR is satisfied when
any child is satisfied, unknown when none is satisfied and any is unknown, and
unmet when every child is unmet. Shared subgraphs are memoized.

Required blockers/questions follow that logic. A failed optional OR branch never
becomes an option blocker when another branch satisfies the OR. An unknown OR
asks about its unresolved branches. Every OR branch retains its own state and
blocker/question node IDs in `alternatives`, including branches not currently
required. Sibling option IDs refer only to published paths of the same rule
version; conflicting versions remain distinct and never get combined.

Nine additive shared definitions under contract `0.1` cover tool arguments,
requirement evaluations, alternative branches/groups, blockers, questions, costs,
options and the result. `RecoveryOptionResult` contains the exact backend query
and input case version, catalog version, sources, scoped options, lookup-level
blockers/questions, official referral and notices. It retains C04's lookup states:
`available`, `unknown`, `no_match`, `unavailable`, `stale`, `conflicting`, `conflict`.
`available` means evaluation of a matching reference succeeded.

Each option carries rule/version/path identity, official destination, evaluated
nodes and separate household access constraints, source attribution, necessary
blockers/questions, OR alternatives, sibling paths, limitations and costs.
`requirement_state` combines the root graph and household access checks:
`satisfied`, `unmet`, or `unknown`. Individual root/constraint states remain visible.

| Option status | Meaning |
| --- | --- |
| `blocked` | A required modeled condition or access constraint is explicitly unmet |
| `provisional` | Answers, agency confirmation, policy coverage or rule currency/version remain unresolved |
| `feasible` | Reserved for a future complete, current, unambiguous reference whose modeled requirements/access checks all pass and whose requirements have no unresolved entries; it still would not itself be an eligibility decision |

The current C04 contract requires `coverage_complete: false`. Accordingly,
matching every modeled Boolean still produces a provisional option. The partial
seed cannot produce a fully feasible option. `household_eligibility` is always
`unknown`. Rule/source review dates, provenance and original limitations are
preserved. Fee, transport amount and cost date stay `null`, with an unknown-cost
question; no financial forecast, zero cost or confirmed saving is invented.

## No-car constraints

In-person paths require an explicit `office_transport_available` Boolean access
answer. Unknown access with a current reported `mobility: no_car` produces a
specific question about another way to reach the office. No car alone does not
rule out transit, a ride or another available means. An explicit false access
answer blocks the office path. An explicit true answer satisfies only that access
check, even when the household has no car.

Online paths separately check `internet_access`. The sourced online renewal path
remains visible when office access is blocked; its agency eligibility, payment
and credential-detail prerequisites can still be unresolved. Resource-directory
presence cannot establish a ride or capacity. Access constraints have no policy
source IDs and are separate from the published DMV graph. Proof/exception
requirements remain in their own separately scoped program.

## Validation, access and persistence

`planner/evaluator.py` is pure and deterministic for the same case/rule/query
inputs. C04 validates unique nodes, valid roots/children, nonempty groups,
required leaves, reachability, source attribution, acyclicity and depth before
any evaluation. Cycles and dangling/missing requirements cannot yield partial
usable options: invalid catalogs return `unavailable` with no options, and an
injected malformed result is rejected by the adapter. An absent household
answer instead yields a valid unknown evaluation.

Limits remain four matching rule versions, four paths per version, 32 nodes per
path and eight graph levels. The evaluator returns at most 16 options, preserving
OR groups without expanding combinations. The existing registry result/context
limit also applies.

The adapter authorizes the case before reading shared knowledge, requires the
exact backend query, and rechecks case version/deadline before returning. A
concurrent correction discards all options and sources and blocks later scoped
lookups/writes in that run. Expired work cannot return usable options.

Evaluation changes no case version, audit, plan, task, snapshot attribution,
finance ledger, application or published knowledge. The ordinary chat path still
stores the user/assistant turns through CaseService. Completed-turn replay uses
the saved reply without repeating evaluation. No snapshot field, HTTP handler or
public command type was added.

## Evidence and user checks

28 focused planner checks plus two new real pinned-Strands checks pass. The
planner/rule/SDK run passes 75 checks. Evidence covers nested AND/OR alternatives,
unnecessary-branch suppression, missing/invalid/stale/conflicting/future facts,
agency provenance, no-car access, partial proof scope, unknown costs, graph cycles,
shared subgraphs, isolation, no writes, restart, deadlines, concurrent changes,
exact queries, opt-in schemas, saved replies and replay. The live-smoke assertions
are exercised through a synthetic provider; Codex loads no private configuration.

The selective shared-checkout run passes all 288 non-HTTP checks, including 55
finance checks introduced by concurrent work. Later full discovery runs 295
checks: 290 pass, including 57 concurrent finance checks and 19 real-SDK checks;
the five HTTP checks fail at host-prohibited loopback binding and require an
unrestricted local run. Concurrent finance work is untouched by this slice.
The C05 addition itself contributes 30 checks to the previous 208-check baseline.
Counts describe this checkout at this milestone.

Run from the repository root:

```sh
# Focused synthetic planner/rule/SDK regression: 75 checks
.venv/bin/python -W error::ResourceWarning -m unittest tests.test_planner tests.test_program_rules tests.test_strands_agent -q

# Full local suite, including the five loopback HTTP checks
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q

# User-run live Sonnet 4.5 planner proof on a disposable synthetic case
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --planner
```

The live mode enables its own planner flag and disables other optional groups.
It seeds explicit CO/lost-ID/no-car, unavailable office transport and available
internet facts. A pass requires the tool's provisional online/blocked office
paths, unknown costs/eligibility, sources, a saved reply describing both routes
and an official URL, unchanged household domains/catalog and replay without
another evaluation. Safe log records use `mode: planner`. It needs no running
HTTP server or new source fetch. Codex does not run this credentialed command.

## Remaining C05 work and verification gates

Typed evidence/action links, trusted agency confirmations,
cross-action dependency planning, priority/deadline
ordering and dated cost/finance integration remain separate slices. P2 review of
the additive result boundary and the full contract freeze remain pending. The
first slice is ready for integration; full C05 is neither integrated nor verified.

Colorado live rule extraction remains unverified after the HTTP 403. The prior
USAGov fetch and Sonnet fetched-reply/replay proofs remain verified independently.
Evaluation consumes the reviewed published catalog and cannot turn that public
fetch proof into Colorado eligibility or policy approval.

## Saved plan revision — second slice ready for integration

`STILLHERE_AGENT_ENABLE_PLAN_REVISION=true` independently registers
`revise_recovery_plan` with the same program/optional exact-version arguments.
It defaults to false and does not register read-only evaluation or other optional
tools. There is no public `plan.update` command. The model cannot submit a plan,
facts, costs, sources, case identity, role or commit authority.

`CaseService.revise_agent_plan` authorizes the household/run, locks the transaction,
reads validated published knowledge and recomputes the deterministic evaluation
from the current case. It checks expected version, active lease and deadline
before saving. Unknown/no-match/stale/conflicting references return
`needs_clarification`; failed knowledge reads return `unavailable`. Both retain
the previous plan. A concurrent version mismatch returns `conflict`.

Successful revision atomically saves plan/actions, source attribution, one case
version and a prior-case audit event. The plan version increases, `computed_at`
and source `input_case_version` remain explicit, and derived finance becomes
pending without changing its ledger. Feasible/provisional/blocked evaluation
maps to ready/waiting/blocked action status. Current partial policy produces a
provisional plan, with unknown eligibility, costs and deadlines.

Each `RecoveryPlanAction` stores its rule/version/path, evaluated requirements,
household access constraints, questions/blockers, supported alternative IDs,
unknown costs, pinned public source records and user-report history. Stable IDs
derive from program/path, so a rule version change cannot discard completion.
Completed actions retain their original report, requirements and source records;
skipped actions retain the household decision. Removed paths remain visible with
`is_current: false`. Unrelated program/legacy actions are preserved.

Fact corrections mark owned input evaluations stale. Revising one program cannot
refresh another program's evaluations: per-action fact/catalog identity and
`input_freshness` keep those records stale and the overall plan pending until the
affected program is reassessed. Completion remains a household report even when
its historical requirement evaluation is stale. No source time is fabricated.

Same-turn identical domain inputs resolve to one stable child event despite the
commit's own case-version increment. Changed facts, explicit task reports or a
new catalog permit another revision. Replay does not repeat effects; duplicate
effects encountering a concurrent change block later writes rather than silently
reconciling authority. Storage failure rolls back snapshot and audit together.

## Task reporting and reassessment — third slice ready for integration

The existing public `task.update` command is now implemented for saved planner
actions. It is available through the ordinary authorized/versioned command API.
`STILLHERE_AGENT_ENABLE_TASKS=true` independently exposes the `update_task` adapter
to the model (default false). Three mutually exclusive payload forms are allowed:

```json
{"action_id":"ID_FROM_SNAPSHOT","status":"completed"}
{"action_id":"ID_FROM_SNAPSHOT","status":"skipped"}
{"action_id":"ID_FROM_SNAPSHOT","inability_reason":"transport_unavailable"}
```

`inability_reason` accepts `no_car`, `transport_unavailable`, `no_internet`,
`missing_documents`, `cannot_pay`, `appointment_unavailable`, or `other`.
An explicit `inability_reason: null` withdraws/resolves a prior inability report
and requests reassessment; it does not declare requirements ready.
Transport/appointment reasons apply only to in-person paths, and no-internet
applies only to online paths. Extra private/authority fields or mixed operations
are rejected. A task ID does not grant access to another household.

Completion/skipping is user-reported, with original occurrence time, separate
receipt time and stable event identity. Future reports are rejected. Completed
work cannot be undone by skipping/inability; correcting completion is a later
explicit correction workflow. No report supplies eligibility, agency approval,
evidence predicates, consent or financial amounts.

Inability immediately reassesses the affected route: a definite inability adds
a reported blocker; no-car/other adds clarification while retaining other
transport as unknown. Other sourced alternatives keep their own states. The plan
is marked pending; a requested `revise_recovery_plan` recomputes requirements and
preserves the explicit report. Resolving inability clears only its reported
blocker/question, leaving source-backed blockers and unknown requirements intact.

Task effects use the existing atomic event/version/audit path and agent leases.
Repeated commands/agent effects do not duplicate history. The snapshot retains
64 recent reports per action and 32 recent revisions; prior complete states and
commands remain in CaseService's durable audit. Plans retain at most 32 actions;
capacity failure rejects the revision without removing work.

## Compact model boundary and current validation

Seven additive `0.1` definitions now cover revision arguments, task payloads,
report history, owned actions, action/plan summaries and `RecoveryMutationResult`.
Plan metadata is additive to the existing snapshot. C01's public command result
still contains the full authorized snapshot. The two new agent write tools return
the same event/status/version/issues fields plus a bounded `plan_summary`.
Summaries expose action IDs/statuses, official destinations, alternatives,
freshness and unknown costs/eligibility. They show at most four blockers and four
questions, with total counts and an explicit truncation flag.

The initial model context uses this summary for saved planner records. Full
requirements, pinned sources and history remain in `CaseSnapshot` and `read_case`.
This avoids repeating large requirement graphs through every write call; omitted
diagnostics cannot be treated as satisfied. The service checks the summary output
limit before commit, so an oversized result cannot save an undisplayable effect.

31 lifecycle/smoke checks and two additional real pinned-Strands checks pass.
The focused lifecycle/evaluation/rule/SDK run passes 108 checks. Current discovery
contains 330 checks; all 325 non-HTTP checks pass, including 21 SDK and 59 finance
checks. The five existing HTTP checks remain pending under the documented host
loopback restriction; their health assertion includes the new command. Concurrent
finance/frontend work is preserved. All checks use synthetic configuration,
temporary cases or scripted models, with no private environment loading.

The user runs:

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --plan
```

`--plan` enables its own revision/task tools, disables other optional groups and
uses a disposable synthetic CO/no-car case. It requires a saved sourced plan,
one explicit reported completion, a second revision preserving that completion,
unknown costs/eligibility, a sourced saved reply, unchanged facts/ledger/policy
and replay without more tools. Its bounded proof allowance is at least six model
turns and 24,000 cumulative tokens for the three-step workflow; ordinary runtime
defaults stay unchanged. Safe logs identify `mode: plan`. The read-only
`--planner` proof remains independent. The safe diagnostic log records a passing
read-only `--planner` run. The user-run `--plan` attempt failed on its first model
request with `ValidationException` / `unclassified`, before any tool completed;
saved-plan/task live verification remains pending. The user also reports all
330 tests passing locally with ResourceWarning treated as an error, including
the five HTTP checks blocked in Codex’s environment. C05 remains IN_PROGRESS for the remaining gates above;
no deployed/UI or full-component verification is claimed.


Provider compatibility follow-up (2026-10-11): the new `update_task` tool exposed
`TaskUpdatePayload`'s top-level `anyOf`, matching Anthropic's reported rejection
of top-level tool-schema composition. Its model-facing schema now uses the
existing object properties without root composition; the strict shared union
remains authoritative in the raw-input hook and CaseService validation. The
outgoing Bedrock request test now includes revision/task tools and verifies
this envelope, with invalid task combinations still rejected. All 325 non-HTTP
checks pass after the fix. Safe diagnostics classify the fixed rejection phrase
as `tool_schema_unsupported` without retaining raw messages. This is the likely
cause of the prior first-request failure, not a live-confirmed diagnosis; rerun
the user-owned `--plan` proof. Sonnet 4.5 and C09 remain unchanged.


Live C05 plan proof verified (2026-10-11): the user-run safe log now records
two successful `mode: plan` runs at 12.444 and 13.516 seconds, each with three
completed tools. The proof requires two accepted plan revisions, one retained
user-reported online completion, blocked office access, source records, unknown
eligibility and costs, provisional plan state, a saved reply containing the
official online URL, unchanged facts/ledger/policy and an identical replay
without additional plan/task calls. The synthetic case database is disposable;
no agency submission, eligibility confirmation, fresh Colorado extraction or
full C05 readiness is established. Live save/report/preserving-revision/replay
verification is now passed following the provider schema fix.
