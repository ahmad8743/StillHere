# Independent backend MVP acceptance

October 11, 2026. **Integrated MVP acceptance is not established. Deployment remains gated.**
This audit owns only `tests/test_mvp_acceptance_parallel.py`, new
`tests/acceptance_support/` files, and this handoff. Existing uncommitted work,
application files, shared tests, contracts, README and shared progress documents
were preserved. Handoffs and additive schemas were reviewed as proposals.
CaseService performed every durable case mutation in the new tests. SQL was used
only to inspect disposable databases and install deliberate rollback fault triggers.
No private configuration, AWS credential file, credential value, live model,
live source request, outreach, frontend or deployment was accessed or executed.

| Readiness axis | Current evidence | Decision |
| --- | --- | --- |
| Independent acceptance-test slice | 59 executable checks; no skips or expected failures; synthetic disposable cases | Delivered and reproducible; intentional failing gates remain visible |
| Current-checkout integrated behavior | 42 checks pass; 14 checks block; three real HTTP checks blocked by host binding policy | NOT ACCEPTED; a passing subset cannot establish full MVP readiness |
| Detached boundary proposals | Three independent cost/application checks pass without changing saved cases | Slice evidence only; durable graph/cost/evidence/reassessment assembly pending |
| Existing regression suite | 685 selected checks: 683 pass, two existing fixture errors; existing HTTP tests explicitly excluded | Not a green regression gate; includes domain/proposal/mock checks, separate from independent acceptance |
| Live-provider/model verification | Adapter owner's executable assertions coordinated; no new live evidence obtained here | PENDING_USER_RUN after shared assembly |
| Target operational verification | Deployment owner supplies assets and user-run drills; target transport, Linux/native tools and service drills unverified here | Pending; no installation or production-readiness claim |

The final acceptance run recorded `2026-10-11T08:37:42Z`, after the last observed
adapter registry delivery and three additional regression tests. The report contains
explicit source hashes before/after; no change was detected during that run.
The checkpoint covers 27 named implementation/schema files, not every repository
file or dependency. Later delivery changes require another run. Counts include
duplicate demonstrations of a root failure (family journey and finance gate),
so they are **checks**, not a count of unique defects.

## Executable evidence and reruns

Run from the repository root. These commands neither load environment files nor
discover user credentials. Default acceptance includes all groups and exits
nonzero on a failed, blocked, skipped, or source-changing run.

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.run \
  --report tests/acceptance_support/evidence/current.json

env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.regression \
  --report tests/acceptance_support/evidence/regression.json
```

Saved reports: [acceptance](../../tests/acceptance_support/evidence/current.json)
and [regression](../../tests/acceptance_support/evidence/regression.json).
They contain status/test IDs/source hashes, not bearer tokens, case records,
provider text or household data. The regression runner uses qualified discovery
(`top_level_dir='.'`) to keep IDs importable and stable. Earlier unqualified
discovery exposed a proposal import issue; the adapter owner subsequently added
name normalization. The two genuine legacy fixture errors still reproduce.

Focused reproduction:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.run \
  --group transactions --group offline-handler
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.run --group gates
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.run --group proposals
```

The transactions group intentionally includes the failing full journey. It is
not a curated green subset. Proposal tests operate on detached copies of real
saved cases, never commit a fabricated plan to make integration appear present.

**Real HTTP is blocked**, including an approved unrestricted retry:
`PermissionError: [Errno 1] Operation not permitted` at loopback bind. The three
offline tests call the real HTTP Handler methods using in-memory request streams;
they prove dispatch/body validation only. They do not prove sockets, headers on
the wire, disconnect handling, deadlines or server lifecycle. Exact user-run
transport command, requiring no credentials or running service:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m tests.acceptance_support.run \
  --group http --report /tmp/stillhere-http-acceptance.json
```

Expected: three tests pass, zero failures/errors/skips, unchanged source hashes,
and no `blocked_http` entries. This command starts the actual CaseHTTPServer on
an ephemeral loopback port and exercises persisted finance/replay/isolation,
strict JSON/version/body handling, and scoped operator access/revocation. A pass
establishes only this transport slice. After any integrated delivery, rerun the
default suite, regressions, and the real HTTP group; retain new sanitized reports.

## Requirement-level readiness matrix

`Verified` means the named bounded synthetic behavior is implemented and checked
in this checkout. `Blocking` includes missing assembly or verification, even
where a pure domain slice passes. `Needs explicit deferral` is a blocking scope
decision, not an accepted waiver. Existing specification deferrals are identified
separately. Test identifiers below are methods in
[the acceptance suite](../../tests/test_mvp_acceptance_parallel.py); class/group
names identify the reproducible selection. Component labels follow the shared
contracts; no full-component readiness is inferred.

| ID / requirement | Status | Evidence and remaining boundary |
| --- | --- | --- |
| R01 — C01 partial intake, unknown/skipped values and distinct current/damaged/issuing locations (§3–4, §12) | Verified, bounded | `FamilyJourneyTests.test_skipped_intake_and_distinct_locations_do_not_share_location`; real CaseService creation/corrections. Declining location does not imply absence or consent. UI bypass/accessibility is R33. |
| R02 — Full mother/two-children/lost-home/documents/$300 journey (§12) | **Blocking** | `test_complete_synthetic_family_journey_uses_persisted_records`: intake, catalog referral, saved plan and application succeed; explicit finance calculation rejects valid input, stopping final publication/restart assertions. No complete journey pass. |
| R03 — Canonical 14-day finance (§8, §12) | Verified | `test_all_four_canonical_finance_scenarios_through_commands`: day-5 $55 gap; covered week yields day-11 $25 gap; day-8 hypothetical $500 ends $280 without a gap; day-12 receipt retains earlier $25 gap and ends $280. Actual money remains $300. |
| R04 — Unreceived/denied/delayed aid, restrictions, overlapping support, transfers, unknown inputs (§8.1–8.3) | Verified, bounded | Six `FinanceIntegrityTests`; approved aid never becomes accessible cash, support not cash/double coverage, transfer not income, incomplete costs visible, ambiguous spending has no ledger/forecast write, Boolean money rejected. Imported provider lifecycle is R34. |
| R05 — Explicit calculation and same-state chat/direct financial updates (§3.3, §8.3) | **Blocking** | `test_explicit_finance_recalculation_accepts_current_inputs` rejects `changed_record_ids`; `test_new_finance_adapter_chat_control_parity_requires_real_case_service` raises `extension_integration_required`. Existing command path passes; extension factories are unapplied assembly. |
| R06 — No-car reassessment and preserved completed/unrelated actions (§3.3, §12) | Verified, bounded; full cost lifecycle **blocking** | `test_no_car_replanning_preserves_completed_work_and_unrelated_program`: completed online action retained, mobility-sensitive office route changes, unrelated program retained with honest staleness. Does not prove dated cost/dependency persistence; R07–R08. |
| R07 — Typed dependencies, circular ID/birth-certificate blockers, alternatives, priorities/deadlines, correction propagation (§7, §12) | **Blocking** | Planner/boundary pure slices exist and regression runs include their checks. Actual revision path invokes `evaluate_options`/`revise_plan` without persisted cross-action graph assembly. Graph/evidence/confirmation authority, revisions/fingerprint and cycle resolution require owner assembly and durable acceptance. Honest official-confirmation fallback remains required; no invented route. |
| R08 — Selected recovery costs, protected essentials, null costs, finance-driven relevant reassessment (§8.4) | **Blocking** | Three `ProposalBoundaryTests` verify dated-null comparison stays incomplete, undated costs suppress the whole proposal, baseline/essentials remain unchanged. Current shared alternative adapter rejects nullable amounts; cost metadata/graph shared schema and `planner_effects` consumer are pending. A queued proposal alone does not revise a plan. |
| R09 — Completion reports and auditable correction (§3.3–4) | Completion preservation verified; correction **blocking** | `test_completion_correction_is_auditable_durable_and_replay_safe` rejects reviewed additive completion reference/reason payload. New branch must preserve original report/time/history, stale only dependent active work and replay once. No automatic expense reversal. |
| R10 — Changed facts/evidence/rules invalidate application preparation without losing reports (§3.4, §7) | **Blocking** | `test_fact_correction_invalidates_application_preparation_preserving_stage`: submitted stage retained, but issuing-jurisdiction correction leaves preparation `provisional`. Evidence-specific invalidation, rule-publication/expiry fanout and re-preparation also need durable review/tests. |
| R11 — Household application stage/correspondence, no agency/money inference (§3.4) | Verified, bounded | `test_application_stage_and_correspondence_do_not_create_money_or_agency_outcome`: approval is a report, not agency evidence or received money. Draft preparation stays provisional/unknown and external submission is user-controlled. |
| R12 — Report-only application status during rule/source outage (§10) | **Blocking** | `test_reported_application_status_saves_while_rules_are_unavailable` returns `unavailable` and does not save report. Detached boundary works. Route typed unavailable through report-only; evidence edits still require a current rule and combined invalid intent must be atomic. |
| R13 — Household cannot mint planner ownership or verification (§5, §10) | **Blocking** | `test_household_finance_cannot_mint_backend_planner_ownership`: household `set_commitment` accepts `origin`, planner IDs, rule IDs/version and actual-event ownership labels. Reserve backend provenance before enabling cost reconciliation. Trusted confirmations/agency receipts must remain backend-selected IDs, default empty/fail closed. No trusted acquisition provider is implemented. |
| R14 — Lost response/restart/replay, changed event intent and version races (§4, §8.3) | Verified | `TransactionTests` reproduce one spending effect after reopen/replay, changed payload rejection, cross-household denial and two independent SQLite writers: one applies, one returns visible conflict; intent cannot change on retry. Creation replay also checked by adapter methods. Client unsynced display is R33. |
| R15 — All-or-nothing writes and stale derived-result prevention (§4–5) | Verified | Finance/worker fault triggers fire after tentative work; ledger, snapshots, events, state/effects/audit roll back. Stale expected version, expired run/deadline and oversized compact result cannot overwrite/publish. No network is involved. |
| R16 — Provider fails after accepted writes, interrupted agent resume (§10) | Accepted-write retention verified; resumed interruption **blocking** | `test_provider_failure_after_write_retains_effect_and_replay_does_not_invoke_provider` and interrupted lease/new-claim test pass. `test_expired_agent_run_is_visible_on_resume_after_process_restart` still returns `running` on read; failure appears only on another claim. No automatic provider/effect replay is authorized by these tests. |
| R17 — Same-valued correction followed by reassessment (§7, §10) | **Blocking** | `test_same_fact_report_does_not_leave_replay_plan_permanently_stale`: input correction marks actions stale; fact-only revision fingerprint returns `already_applied`, keeping them stale. Replay identity must include actual relevant input generations/history. |
| R18 — Scoped bearer session and household isolation (§10) | Verified, bounded | Household and operator tests plus offline handler deny foreign reads/writes/replays and role spoofing; token alone must match owner. DB stores token digests. Anonymous recovery/lifetime/erase decisions are R30. |
| R19 — Operator server-side provisioning, minimal projections, scopes/revocation, ownership and audited operations (§9–10) | Verified, bounded | `CheckInOperatorTests` check read-only scope, explicit server provisioning, per-case assignment/replay, revocation, no full finance/household snapshot or public provisioning route. Operator IDs cannot steal assignment. Transport still R29. |
| R20 — Operator projection access audit (§10; check-in handoff) | **Blocking** | `test_operator_read_is_access_audited_with_minimal_metadata`: reads leave no durable access audit. Record allowed/denied reads with actor/scope/time/outcome, no bearer/message/private request body. Concurrency with revocation must fail closed. |
| R21 — Agreed reminder → overdue/unknown → review without chat (§9, §12) | Verified, simulation only | `test_reminder_overdue_acknowledgment_late_reply_attempt_and_outcome`: controllable clock, one reminder/review, simulated ack/attempt/outcome persist, original report and receipt times retained. Missed app activity alone creates no follow-up. |
| R22 — Help, decline, pause, check-later, enrollment consent (§3.5, §9) | Verified, simulation only | Help produces immediate official urgent guidance and review; pause prevents future attempts, check-later reschedules once, no enrollment/share/system authority through model allowlist. Help-request adapter parity remains pending extension assembly and exact household consent review. |
| R23 — Independent optional location, clear/expiry/purpose/access (§3.5, §10) | Verified, simulation only | Location tests separate damaged/current/shared places, age/expiry, assigned-handler policy and clear; old/removed coordinates never assert current presence/condition/destination. No continuous tracking. |
| R24 — Independent worker duplicate/crash/restart effects (§9, §12) | Verified locally | Two actual worker processes produce one effect set; SIGKILL after committed work then restart has no duplicate. SIGKILL inside a real CaseService transaction proves rollback across snapshot/private state/effects/audit; ordinary restart catches up once. Fault probe only adds a synchronization pause, no domain writes. Target registration/reboot/fairness are R32. |
| R25 — Dashboard descriptor allowlist and persisted-record references (§9) | Verified, bounded | `OutputAndBudgetTests.test_dashboard_reference_allowlist_replay_and_rejection_preserve_previous_components` rejects dangling/cross-kind/code/authority arguments and retains last publication. Renderer and export are R33. |
| R26 — Source/derived freshness on return (§6, §9–10) | **Blocking** | `test_dashboard_metadata_recomputes_source_expiry_on_authorized_read`: component remains old `unknown` after referenced source expires; expected `stale`. Saved display metadata is frozen. Recompute authorized projection from current backend clock without changing publication identity. Full pending plan/application rule expiry is R07/R10. |
| R27 — One/two skippable structured questions; saved exact-turn answer provenance, multi-choice/replay/stale/forged answers (§3.2, §9) | **Blocking** | Three gates: structured provider reply is `failed`/`invalid_agent_reply`; arbitrary orphan `choice_id` is `applied`; multichoice/replay/stale/skip assertions cannot execute past reply failure. After assembly, replay must precede correlation validation, and answers cannot execute arbitrary commands or consent. |
| R28 — No declaration, source outage/stale retained referrals and truthful availability (§6, §12) | Verified offline; live **pending** | Three `SourceAcceptanceTests` run the real incident facade with injected empty/failing transport and real reviewed resource catalog. No-match ≠ unavailable ≠ universal ineligibility; prior stale referrals retained on failure. No live capacity/eligibility is inferred. Historical live feed evidence in shared progress stays historical. |
| R29 — Real HTTP adapter (§5, §10) | **Blocking: verification environment** | Three actual transport tests bind-denied even after approved retry; exact user command above. Three in-memory Handler checks pass and remain separate evidence. Deadline/disconnect/saturation tests are still unverified, not implicitly covered by dispatch. |
| R30 — Anonymous session loss/recovery/expiry and private demo erase (§10, §14) | Recovery explicitly deferred; lifetime/erase **needs explicit decision** | Sessions persist digest+created_at; authorization checks existence only, with no household expiry/rotation/revocation/clear API. Saved token resumes after reopen; lost token cannot be recovered from case ID. Public account recovery is deferred by §14. Define private-demo token custody, lifetime and reset/erase procedure; do not imply lost-device recovery or silently choose TTL. Public retention/onboarding policy is a separate pilot. |
| R31 — Per-run/concurrent/provider budget and interruption bounds (§5, §10) | Per-run slice verified; global bounds **blocking** | Terminal tool budget/no late writes and per-case durable exclusive claim pass. Config accepts positive budgets without upper ceilings; current server/provider/continuation threads lack global capacity bounds. Timed-out daemon provider can keep running although its writes are revoked. Deployment owner has exact unapplied capacity/drain patches; owner must choose budget and verify actual capacity, timeout and overload behavior before exposure. |
| R32 — Operational durability, worker fairness, host/TLS/backup/restore (§2, §10, §13) | **Blocking for deployment; some target choices need explicit deferral** | Local transactional worker proof is present. Worker `batch_size` limits changed cases, not all selected IDs/scan/transaction time; fairness/SQLite contention/SIGTERM latency at target load unmeasured. Finance computes inside `BEGIN IMMEDIATE`, so simultaneous HTTP load can hold writer lock. DB mode is 0600/WAL; target restart/reboot, FULL-sync choice, native units/Caddy, trustworthy IP TLS/renewal, notification visibility, off-host restore/RPO/RTO remain user-run deployment gates. No paid destination/alert choice inferred. |
| R33 — Mobile UI, accessibility, offline cache/visible unsynced edits, SMS-style simulator, printable/minimal export/erase (§9, §12) | **Out of scope for this backend assignment; still required globally** | Stable event IDs/replay/late receipt are backend evidence. No frontend/cache/text renderer/export work performed. Backend replay is not proof of local household scoping, opt-in local saving, unsent help display, erase controls or usable offline contacts. Do not waive the whole prototype journey. |
| R34 — Plaid/imports, live SMS/welfare/field response, background GPS, raw document OCR/vault, full console (§8.5, §14) | **Explicitly deferred / out of scope** | No Plaid or frontend work; manual finance required. Live welfare outreach/field response and continuous GPS explicitly deferred. Live conversational SMS optional; labeled simulator remains required globally. Production bank/provider/import lifecycle not a hidden acceptance dependency. |
| R35 — Nationwide referrals, bounded detailed jurisdiction/rules and actual Strands/Bedrock demonstration (§6–7, §12–13) | Slice evidence; **live pending / coverage needs honesty** | Reviewed routing and CO demonstration path exist; referrals outside detailed scope must remain labeled. Earlier national live/existing planner proof is retained as historical owner evidence. CO official-page live extraction/403 fallback remains a separate unresolved proof; an honest official referral can be reviewed as fallback, not a verified extracted rule. New registered finance/application/dashboard/no-car tools require user-run genuine live calls below. |
| R36 — Malicious external text cannot expand backend authority/shared policy (§5, §10) | Guardrail slices present; complete integrated exercise **blocking** | Existing regressions cover allowed-tool/source review boundaries; independent tests reject model consent/operator authority and descriptor code. New extension raw argument validation/default-off flags and source text separation are review proposals. A grounded source/model transcript cannot grant trusted receipts, publishing authority or outreach. R13/R27 and shared raw-input wiring must pass integrated tests. |

## Reproduced failures and exact review proposals

Every failed gate is an ordinary assertion/error. None is skipped, marked expected,
converted to a mocked pass, or repaired by editing application/shared tests.
Reproduce one case by passing its qualified test ID to `unittest`, for example:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest -v \
  tests.test_mvp_acceptance_parallel.RequiredIntegrationGates.test_household_finance_cannot_mint_backend_planner_ownership
```

| Failure / synthetic trigger | Expected | Actual in preserved checkout | Proposed fix / owner review |
| --- | --- | --- | --- |
| Seed canonical ledger; call real derived `finance.calculate` | Applied baseline with $55 day-5 gap | Rejected: `invalid_input`, field `changed_record_ids`, bounded string-array expected | Normalize tuple default to list; stamp calculation with committed version; exact acceptance patch and adapter patch overlap |
| Invoke enabled extension `update_financial_state` against actual CaseService | One $12 expense, actual cash $288; direct/chat parity | `AgentFailure: extension_integration_required` | Review adapter's stable child-event command API, runtime/config/registry/provider raw-input and schema assembly; replay/version/bounds must stay in CaseService transaction |
| Prepare/submit CO application; correct issuer to LA | Preparation pending/stale; submitted report retained | Preparation remains `provisional` | Exact fact invalidation patch; boundary owner's evidence/rule/expiry lifecycle also required |
| Same saved application; typed rules-unavailable injection; report submitted | Save household stage with retained pending draft | `unavailable`, no report saved | Typed outage report-only boundary patch; never fall back on arbitrary validation/programming errors |
| Mark task completed; correct by original event ID/reason | Append correction, preserve original, invalidate dependent active work; replay once | Shared payload rejects proposed fields | Boundary schema/commands correction branch proposal; graph assembly dependency |
| Publish source-details card; advance clock beyond source expiry | Current read shows stale | Old component freshness stays `unknown` | Read-time projection refresh, retaining publication ID/time; exact acceptance proposal |
| Claim one-second agent run; reopen after expiry and only read | Durable terminal `agent_interrupted` display | Turn stays `running` | Existing audited expiry transition on authorized resume read; no provider restart; exact acceptance proposal |
| Revise plan; send identical issuer fact again; revise same program | Reassess marked-stale inputs | `already_applied` keeps actions stale | Include input event generation in revision replay identity; full evidence/cost/dependency/version fingerprint still needs boundary owner |
| Send nonexistent orphan choice ID | Reject without case effect | `applied` | Guard orphan choice fields plus reviewed complete-turn/question correlation and cardinality assembly |
| Provider returns bounded text+two optional questions | Persist complete turn and questions | `failed` / `invalid_agent_reply` | Reviewed structured-reply output staging + CaseService finish validation; then test multi-choice, forged/stale/replay/skip paths |
| Read scoped operator queue; foreign/revoked reads | Minimal durable granted/denied access records | No access audit table/records | Transactional authorization/projection/audit wrapper; exact acceptance proposal |
| Household sets commitment with invented planner ownership/rule/actual-link metadata | Reject; authoritative case unchanged | Accepted and retained | Exact recursive reserved-provenance validation patch; backend trusted origin must be established outside household/model arguments |

[shared-fixes.patch](../../tests/acceptance_support/shared-fixes.patch) contains
exact review-only diffs for CaseService, commands, integration, planner service,
and the two legacy shared fixture updates. **It was not applied.** Six proposed
Python sources compile in memory and `git apply --check` passes against this
checkpoint; those are syntax/applicability checks, not behavioral verification.
Regenerate only after reviewing changed baselines:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m tests.acceptance_support.proposals
git apply --check tests/acceptance_support/shared-fixes.patch
```

The two regression errors are
`tests.test_case_service.CaseServiceTests.test_correction_retains_completed_work_and_marks_old_results_pending`
and `tests.test_intake.IntakeTests.test_partial_updates_preserve_prior_facts_needs_and_completed_work`.
Both preexisting tests install an abbreviated `{input_case_version: N}` forecast
through SQL; the now-strict C08 projection rejects it, leaving `case_snapshot=None`.
Proposed diffs retain assertions and generate the fixture using the authoritative
finance function. Do not weaken validation or alter our acceptance tests to pass.

Additional exact proposals already supplied by the respective owners:

- [Agent extensions](agent-extensions-handoff.md):
  `backend/stillhere/agent_extensions/integration_proposals/shared-wiring.patch`
  and `domain-dependencies.patch` for shared agent/config/service/commands/schema,
  direct consent and structured-answer assembly. Provider/schema copies and
  disposable patch tests are review evidence, not accepted shared contracts.
- [Domain boundaries](domain-boundaries-handoff.md): exact shared command,
  integration, service and additive schema assembly for correction, provenance,
  costs, application/evidence invalidation and queued finance requests. The
  deterministic `complete_planner_effect` consumer and comprehensive revision
  fingerprint are still expressly missing. Do not treat the queue as completion.
- [Deployment](deployment-final-handoff.md): exact server/runtime concurrency,
  SQLite durability, shared test/documentation proposals. Static applicability
  and isolated-copy checks do not establish current checkout or target readiness.

Overlapping diffs must be reconciled, not concatenated or force-applied. The
integration owner exclusively owns their application and shared readiness edits.
This audit proposes no additional README/progress edits; copy the gate evidence
only through the owner. Existing `contracts.py`/server extension wiring proposals
have explicit zero-diff cases in the adapter handoff, subject to owner review;
transport capacity proposals remain a separate server diff.

## Live and operational evidence remains pending

The adapter/Bedrock chat **Build household agent adapters** received this audit's
failures and confirmed executable live-proof routing in its handoff. Evidence
ownership remains there; no new credentialed/model result is claimed here.
After shared assembly and synthetic acceptance, the **user** may run:

```sh
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode finance --run-live --env-file .env.local
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode applications --run-live --env-file .env.local
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode outputs --run-live --env-file .env.local
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode no-car --run-live --env-file .env.local
```

These are instructions only: Codex must not load that file or run credentialed
commands. Omit `--env-file` if the user's environment is already configured; AWS
uses the external credential chain. Keep the configured model/region; never paste
credentials. The no-car mode additionally requires reviewed domain dependencies.
Commands create disposable synthetic cases and must exit zero with sanitized
allowlisted JSON, complete saved turns, genuine successful new tool invocations,
grounded outputs, exact reopen equality and replay without further effects.

The [adapter handoff](agent-extensions-handoff.md) supplies executable assertions:
finance has one 1,200-cent expense, 28,800 cash and explicitly hypothetical
33,800 scenario; applications retain user-reported submitted/provisional state
without money/agency invention; outputs persist approved descriptors/questions;
no-car persists dated-null cost as incomplete with null ending projection and
honest online/office constraint labels. Text-only output, refusal, scripted model,
SDK mocks or historical tool families cannot satisfy this new live gate.
Failures keep verification pending; only actual safe successful evidence can
upgrade the live column, independently of integrated acceptance.

For target transport/TLS/native units, repeated worker/API crashes and reboot,
snapshot/restore and host-loss drills, follow
[deployment OPERATIONS](../../deploy/OPERATIONS.md) and the separate deployment
readiness ledger. They require target access and evidence. No deployment is
authorized before integrated acceptance. Reduced operational bounds, private-demo
session retention/reset, target-load/worker fairness budgets, alert/recovery
destination and any official-source fallback substitution need explicit owner
decisions; they are not already deferred by a passing local subset.
