# C04 reviewed program rules — second-slice handoff

Updated October 11, 2026. **The bounded read-only rule slice is
READY_FOR_INTEGRATION with offline evidence and a user-run live model/tool
proof. All five bounded C04 slices are now READY_FOR_INTEGRATION; the new knowledge failure branch passes live, with Colorado live candidate extraction pending.**
The [referral slice](resource-integration.md) remains available independently.
Keep the working Claude Sonnet 4.5 configuration. C09 implementation is deferred.

## Enable and exercise

Set `STILLHERE_AGENT_ENABLE_RULES=true` in the user's private configuration or
process environment when running the agent-enabled service. It defaults to false
and independently adds `retrieve_program_rules`; it does not enable intake,
incident or resource tools. No additional source credentials or network requests
are needed for this catalog. The default read/fact registry remains unchanged.

The tool accepts only the program identifier and an optional exact version:

```json
{"program_id": "co_state_id_replacement", "version": "2026-10-10.1"}
```

Omit `version` to inspect matching published versions. The backend derives the
issuer from the case's explicit `document_issuing_state` fact: a valid reported
or source-supported US state code, currently `CO` for this seed. Use the existing
`fact.correct` command to record the user's answer. Current location and damaged
residence never establish the document issuer. Unknown, invalid, conflicting or
stale issuer facts produce an unknown lookup without reading the catalog.
Case, session, role, source URL, publication intent and issuing-state arguments
are rejected before lookup. Credential numbers and proof documents are not inputs.

## Published reference seed and source review

`backend/stillhere/knowledge/program_rules.json` contains catalog
`2026-10-10.rules.2`, retaining program `co_state_id_replacement`, version `2026-10-10.1`, and adding the separate partial `co_state_id_proof_options` reference.
It is a reviewed, seeded **partial reference**, with `coverage_complete: false`;
its `published` label means included in the read-only catalog. Lookup remains read-only. The separate [fetch/review slice](knowledge-review-integration.md) supplies public submissions and explicit local manual publication; pending candidates never enter lookup.

Production pages were read in the browser at `2026-10-11T02:24:54Z` (October 10
locally), including the relevant expanded FAQ sections:

| Official source | Supported scope |
| --- | --- |
| [Colorado DMV replacement page](https://dmv.colorado.gov/replace-your-lost-stolen-or-destroyed-driver-license/permit/cdl/id) | Lost or severely damaged state IDs are processed as renewal; online renewal may be possible, otherwise arrange an office appointment. |
| [Colorado DMV renewal page](https://dmv.colorado.gov/renew-your-colorado-driver-license-permit-or-id-card) | Partial online prerequisites include prior credential details, email and payment; office renewal requires an appointment and applicable documents. Full eligibility needs official confirmation. |

Search results included old development/demo pages and an older duplicate-license
form. Those were excluded. The production replacement page distinguishes
driver-license/permit/CDL duplicate and mail routes from state-ID renewal; those
license routes are not applied to this seed. The automated web reader received
403 responses, but the production pages and FAQ content were available in the
browser. This review is not a live provider or household eligibility test.

Two paths are returned: possible online renewal and office renewal. Each path
contains a flat, source-attributed graph with `all_of`, `any_of` and `requirement`
nodes. Lost/severely damaged conditions are alternatives within each path.
Leaves describe availability, actions or authority confirmation; all evidence
states stay `unknown`. Prior credential details belong only in the official
portal, not in shared knowledge or chat. The tool does not evaluate prerequisites.

The separate proof-options reference adds selected identity, SSN, address and exceptions alternatives with explicit applicability gates. Full proof lists and complete online eligibility,
current fees, transport/appointment access and policy effective dates remain
unresolved. Fees and effective boundaries are `null`, never zero or the review
date. Sources retain their original retrieval/review times, nullable update time,
supporting sections and seeded labels. The 30-day review budget expires at
`2026-11-10T02:24:54Z`; it is a maintenance budget, not a policy effective period.

## Contracts and read-only behavior

Nine additive shared definitions under contract `0.1` cover arguments/query,
requirements/nodes/paths, sources/rules, published catalog and result. No new
snapshot field or public command is introduced by the rule slice.
`ProgramRuleResult` contains the backend query/input version/time, catalog
version, rules, attribution, official fallback and typed notices. Household
eligibility is always `unknown`.

| Result state | Meaning |
| --- | --- |
| `available` | One matching reviewed reference version is within its review budget. Coverage and household requirements can still be incomplete. |
| `no_match` | The bounded catalog has no match for the exact program/issuer/version; other routes are not ruled out. |
| `unknown` | Issuing jurisdiction cannot yet be selected. Ask for its explicit answer and retain the official referral. |
| `conflicting` | Multiple published versions match; retain up to four and require an explicit version or review. Never silently select the newest. |
| `stale` | Review expiry or an explicitly known effective interval prevents current use; retain original records/times for confirmation. |
| `unavailable` | The catalog cannot be read or validated; this is not a no-match result. |
| `conflict` | The case changed during lookup; discard returned requirements and block later scoped lookups/writes in that run. |

Validation enforces official HTTPS source/destination hosts, unique identities,
issuer/jurisdiction/source references, reviewed/published status, bounded nodes,
valid root/child references, reachability, no cycles and at most eight graph
levels. Catalog limits are 32 rules/sources, four paths per rule and 32 nodes per
path; returned rule versions are bounded to four. Duplicate JSON keys are
rejected. The adapter checks that the result matches its exact backend query,
rechecks scoped case inputs, and discards late results, including deadline
expiry during that recheck. Malformed catalog records cannot become valid policy.

The store has no writes, fetch or publication API. Runtime lookup reads CaseService's active reviewed catalog or an explicitly requested immutable archived version; CaseService owns the separate manual publication operation. Lookup does not alter case
domains, snapshot sources, audit history or finance. `CaseService` still owns
the durable user/assistant conversation and replay behavior. A completed turn's
replay returns the saved reply without another rule lookup. Returned public
source metadata is available to the model for its reply; structured source
projection into a case/UI belongs to a later agreed slice.

## Validation and user-run checks

At the C04 completion milestone, 186 non-HTTP checks passed, including 28 focused rule/store/adapter/
smoke checks and 16 real pinned-Strands SDK checks across implemented tools.
Rule evidence covers unknown issuer, scoped program/version, conflicting and
stale reviews, invalid graphs/sources, failed reads, access isolation, concurrent
edits, late results, exact-query integrity, independent opt-in registration,
durable reply/replay and a scripted disposable smoke. HTTP transport checks
remain pending because this host blocks loopback binding. No credential file
or live Bedrock request was used by Codex. The user-run rule smoke now passes
at 14.992 seconds with `mode: "rules"`; the referral regression passes at
18.535 seconds with `mode: "resources"`. Each has one completed tool call and
a completed run, proving its CLI assertions. The full offline/HTTP suite is a
separate check: current validation passes 203 non-HTTP checks among 208 discovered
checks; the five HTTP checks still require an unrestricted local run.

Run these from the repository root:

```sh
# Complete offline suite, including the five loopback HTTP checks
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q

# Previously passed rule proof; optional regression run by the user
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --rules

# Referral regression, if confirming both C04 paths
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --resources
```

Expect 208 checks with `OK` in the full suite when loopback is permitted. The
`--rules` command enables rules for its own disposable case and explicitly
records synthetic `CO` issuer information. It requires a validated current
rule result, both paths, attribution, a saved completed reply, unchanged domain
state and an unchanged replay version. Success prints
`Live Bedrock read-only rule tool ... passed` and exits zero. It does not require
running the HTTP server or setting the opt-in flag separately.

New safe `smoke_started` and `smoke_passed` records include an allowlisted mode
(`default`, `incidents`, `resources`, `rules`, `knowledge`, `fetch`, `planner`, `access`) in
`var/agent-smoke.jsonl`. Find the latest `smoke_started`, then confirm a later
`smoke_passed` with `mode: "rules"` before the next start. Older logs lack mode;
the latest historical user-run pass at 20.356 seconds confirms general agent
success but cannot by itself establish a C04-specific mode. Safe logs contain
no private values, prompt, program arguments or household records.

All five bounded C04 implementation slices are READY_FOR_INTEGRATION. The
[fetch/review handoff](knowledge-review-integration.md) documents the new official
fetch, structured submissions, local manual authority/publication, partial
proof-options scope, current evidence and remaining user checks. Successful
national source retrieval is verified through strict `--fetch`; Colorado live
candidate extraction remains unverified; the
knowledge failure/discrepancy/reply/replay branch passed live at 13.569 seconds.
Full policy coverage, deeper dependency planning, application preparation, UI
integration, shared boundary freeze and deployment remain separate work/gates.

## C05 evaluation consumer — first slice ready

The independent opt-in `evaluate_recovery_options` tool now evaluates these
published graphs against exact Boolean availability/completion case facts.
`retrieve_program_rules` itself remains read-only retrieval with unknown household
evidence states. C05 returns household evaluations separately, with necessary
AND/OR blockers/questions, every sourced OR branch and sibling path, explicit
internet/office-transport access checks and null costs. Missing/unknown answers
remain unknown; cyclic/dangling graphs cannot become usable options. Agency
confirmation needs trusted source-supported provenance; partial policy keeps
otherwise satisfied paths provisional and eligibility unknown.

The first C05 slice is READY_FOR_INTEGRATION, with full C05 IN_PROGRESS. 28 planner
and two new real-SDK checks pass (75 planner/rule/SDK regression checks). The
shared full discovery later runs 295 checks with 290 passes and the five existing
HTTP loopback-bind errors; this includes 57 concurrent finance checks left
untouched. Live Sonnet/planner proof, plan commits/task history and P2 review
remain pending. Colorado live extraction is still unverified after HTTP 403.
[Planner handoff and user-run tests](planner-integration.md).

C05 also now provides separate opt-in saved-plan revision and task-report tools.
CaseService recomputes these published rules within the scoped transaction;
completed actions retain pinned historical source records, and other programs'
stale evaluations are not silently refreshed. C04 lookup remains read-only and
pending candidates still cannot enter planning. Current lifecycle validation
passes 108 focused and 325 non-HTTP checks among 330 discovered, with five HTTP
checks pending and the new `--plan` Sonnet proof user-run. Colorado extraction
remains unverified. [Latest C05 boundary](planner-integration.md).
