# Household agent extensions and provider proof

Owner: extension slice only. Date: October 11, 2026. Shared sources and all
preexisting uncommitted work are preserved. This handoff and both patch files
are review proposals, not approval to apply a shared contract or deploy.

| Gate | Status |
| --- | --- |
| Owned adapter/structured-output slice | READY_FOR_INTEGRATION: 29 focused checks pass; executable default-off factories delivered |
| Exact proposed assembly in disposable copies | 450 selected checks pass with reviewed proposals applied only to disposable copies; this is review evidence |
| Integrated readiness in the shared checkout | PENDING: integration owner must review/apply proposals and pass assembled acceptance |
| Actual new-tool LIVE Bedrock verification | PENDING: user-run only; no live invocation or credential access performed |
| Full components / production / deployment | No readiness claim; deployment remains gated on integrated acceptance |

## Artifacts and factories

- `backend/stillhere/agent_extensions/`: explicit registry/provider factories,
  strict schemas, independent flags, reply/answer validation, owner patches and
  the executable live smoke.
- `tests/test_agent_extensions.py` and `tests/test_agent_extensions_sdk.py`:
  synthetic temporary cases, direct authorization assertions, pinned SDK and
  actual outgoing Converse request inspection.
- `contracts/parallel/agent-extensions.schema.json`: standalone review proposal.
  Copied domain schemas describe the reviewed baseline; CaseService's shared
  schemas remain authoritative for commit/results. No schema is silently frozen.

```python
from backend.stillhere.agent_extensions import ExtensionConfig, create_registry
from backend.stillhere.agent_extensions.provider import create_provider

registry = create_registry(existing_registry, ExtensionConfig(
    finance_updates=True, finance_calculation=True, finance_scenarios=True,
    applications=True, dashboard=True, check_ins=True, structured_replies=True,
))
provider = create_provider(existing_agent_config)  # real provider factory
```

All seven families default off. The exact environment names are
`STILLHERE_AGENT_ENABLE_FINANCE_UPDATES`, `..._FINANCE_CALCULATION`,
`..._FINANCE_SCENARIOS`, `..._APPLICATIONS`, `..._DASHBOARD`, `..._CHECK_INS`,
and `..._STRUCTURED_REPLIES`. Only `true`/`false` are accepted. Factories never
load an environment file or construct an AWS session at import.

## Owner-review patches

The exact patches are saved in
`backend/stillhere/agent_extensions/integration_proposals/shared-wiring.patch`
and `domain-dependencies.patch`, plus `shared-fixtures.patch` and
`documentation.patch`. The domain patch applies after the first and requires
review of `backend/stillhere/boundaries/` and its owner's handoff. Neither has
been applied to this shared checkout by this slice. Tests apply them only in
disposable copies of public backend/contracts sources.

The main patch covers config, runtime, provider raw-input hook, registry,
existing smoke delegation, commands, CaseService, shared integration and schema:

1. The provider calls `registry.validate_arguments` before SDK argument filtering.
   Extension wrappers also validate original raw `ToolContext.tool_use.input`.
   The finance update union is nested under `{update: ...}`; every provider-facing
   root is an object without root composition or unresolved references. Exact
   `oneOf` exclusivity remains authoritative in the wrapper/domain/service.
2. `CaseService.execute_agent_extension_command(token, case_id, parent_event_id,
   run_id, command_type, arguments, expected_version, deadline, max_result_chars)`
   authorizes the household and active run before result lookup; commits ordinary
   command changes, compact bounds, lease/deadline checks and audit in one transaction.
   Stable child IDs hash case, parent, operation and exact logical arguments;
   they exclude provider tool-use IDs and retry transport versions. Duplicate
   accepted events resolve before version checks. A replay with unrelated newer
   case changes halts subsequent adapter writes rather than adopting a new version.
3. Derivations use existing `execute_agent_derivation` and `domain_summary`.
   The patch fixes `_refresh_finance` tuple/list mismatch and stamps a calculation
   with the committed derived version. Compaction/bounds cannot falsely claim an
   already accepted write was unapplied. Precommit oversized mutations roll back.
4. `prepare_structured_reply` stages bounded plain text/questions in backend run
   context and performs no durable write. CaseService finishes the turn and
   revalidates case/version/TTL inside its transaction. Later domain changes or
   a concurrent write invalidate the staged reply. Failed provider work retains
   accepted domain writes and saves no questions. Ordinary text/Markdown replies
   retain existing compatibility. No provider transcript or SDK session store is added.
5. Explicit answer payloads carry `reply_to_turn_id` and `question_id`; choices
   must belong to that exact complete assistant turn. `choice_id` and `choice_ids`
   are exclusive; single/multiple/text/skip cardinality is enforced. Duplicate
   question/choice IDs, dangling/foreign references, second fresh answers and
   choices on skipped/text questions are rejected. Event replay precedes this
   check, so the original answer retries without another turn/effect. Ordinary
   text is valid without correlation; orphan legacy choice IDs are rejected.
6. Enrollment/location sharing and all operator/provisioning/worker operations
   remain outside the registry and backend agent allowlist. `request_help` accepts
   no consent field: the parent conversation command must already contain an
   exact matching `help_request` with direct authenticated household consent.
   The backend compares the entire payload, not prompt text or a generic model
   consent flag. That additive command field is intended for direct controls;
   frontend/control implementation and review remain owned separately.
7. Household finance cannot mint nested planner ownership, authority or verified
   provenance. Tool input record shapes are strict; actual-event source must be
   `user_reported`. The same reserved-field/provenance validator is proposed in
   shared `validate_payload` so direct controls cannot bypass that boundary.

`contracts.py` already supports the needed schema vocabulary; no edit is needed.
`server.py` already constructs `AgentConfig`/`AgentRuntime`; no route or operator
endpoint is added. These are explicit zero-diff proposals, subject to owner
verification. README/progress changes remain the owner's responsibility; use
this gate table and the reproducible evidence below without upgrading live status.

The separate domain dependency patch proposes the reviewed action-cost boundary
in `_finance_alternatives` and `validate_saved_action_scenarios` before calculations.
Saved cost snapshots remain authoritative: changed/stale/past quotes require an
explicit new scenario update and cannot be silently repriced. It preserves dated
null amounts as incomplete, and blocks unknown dates
without deleting ledger entries. It also routes report-only application updates
during unavailable rules through `update_application_boundary`; new agency records
remain unsupported without a separately reviewed trusted backend resolver.
Application invalidation, completion correction, trusted confirmations and full
planner lifecycle assembly remain dependencies on the boundary owner's shared
proposals/acceptance; this slice does not silently implement those shared APIs.
The [boundary owner's handoff](domain-boundaries-handoff.md) also proposes whole
replacements of several same functions/schema records. The owner must compose
these overlapping proposals; do not apply both whole replacements. Our optional
patch is the smaller cost/report-only/synthetic-smoke subset, not the boundary
owner's full planner-effect/correction/invalidation assembly.

For the no-car smoke, the optional patch adds
`CaseService.seed_agent_extension_smoke_costs`: a local authenticated synthetic
fixture helper, never an HTTP route or model tool. It installs an explicitly
chosen synthetic date with a null fee, through CaseService's transaction/audit.
It cannot establish a real public cost, zero amount, agency eligibility or receipt.
The shared schema needs reviewed additive `RecoveryPlanAction.cost_items` for
that fixture. Without these dependencies the no-car live smoke fails pending.

## Tools

| Family | Tools |
| --- | --- |
| Finance updates | `update_financial_state` |
| Finance calculation | `read_financial_summary`, `calculate_cash_flow` |
| Finance scenarios | `set_financial_scenario`, `compare_financial_scenarios` |
| Applications | `prepare_application`, `update_application` |
| Dashboard | `publish_dashboard_components` |
| Allowed check-ins | `read_check_in_status`, `record_check_in_reply`, `pause_check_ins`, `clear_shared_location`, `request_help` |
| Structured reply | `prepare_structured_reply` |

Money, gaps and scenarios come from the finance module, not model arithmetic.
Actual balances/restrictions/unreceived aid are separate from projections.
Application reports never produce agency verification or received assistance.
Dashboard descriptors reference persisted records; questions are display data,
never executable commands, automatic answers or authority.

## Reproducible offline verification

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest \
  tests.test_agent_extensions tests.test_agent_extensions_sdk -v
```

This command uses Strands `1.59.0` and no credentials/private configuration.
The disposable proposal tests are labeled `test_proposed_*`; they do not prove
that the shared checkout is wired. SDK construction uses scripted models or a
patched boto session before any AWS discovery. Actual outgoing `Converse`
parameters are inspected/validated through the pinned SDK and botocore service
model for every new tool, including the nested finance union. A mocked transport
does not establish live provider compatibility.

**29 focused checks pass, with no skips**, including default discovery naming:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest discover \
  -s tests -p 'test_agent_extensions*.py' -q
```

They cover raw invalid/extraneous/union-mixed/nonfinite/cyclic/oversized inputs,
each default-off family, every tool called through the actual SDK, direct
operator/enrollment/location/help/provenance denial, exact consented help,
cross-household IDs, stale versions, expired runs, precommit oversized-result
rollback, accepted writes followed by provider failure, no duplicate effects,
structured stage/commit races, answer/reply replay, restart, approval without money,
dated null costs, undated clarification and explicit saved-quote refresh.

The related current-checkout regression initially passed **417 checks**. After
the final adapter/boundary additions, **450 selected checks pass** in a disposable
copy with the main/domain/fixture proposals applied:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -m backend.stillhere.agent_extensions.verification \
  --proposed-regressions
```

This deliberately excludes HTTP and the boundary owner's separate overlapping
patch-review test; its pure domain tests are included. It is not a full assembled
MVP or current-checkout acceptance claim. Intentional synthetic provider failure
tests emit RuntimeError/ClientError fixture log lines. The standalone extension
proposal passes Draft 2020-12 schema checking.

Current case/intake/access checks reproduce **two existing errors among 30 checks**:
`CaseServiceTests.test_correction_retains_completed_work_and_marks_old_results_pending`
and `IntakeTests.test_partial_updates_preserve_prior_facts_needs_and_completed_work`.
Both directly inject `baseline: {input_case_version: N}`, rejected by the current
shared finance schema. The exact `shared-fixtures.patch` replaces those with real
synthetic deterministic forecasts/publication metadata; all 30 pass in a
disposable patched copy. Shared test sources are untouched. The schema is not
weakened to accept a fake baseline. The optional documentation patch adds links
and separate gate wording to README/progress/Strands docs without asserting live
or integrated success.

## Mandatory USER-RUN LIVE proof

After the integration owner accepts/applies wiring, run from the repository root
using the existing region/model configuration. No model ID is changed. The user
may explicitly load private configuration through the harness; Codex must not
read or load it. Use the external AWS credential chain; never paste secrets.

```sh
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode finance --run-live --env-file .env.local
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode applications --run-live --env-file .env.local
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode outputs --run-live --env-file .env.local
# Requires separately reviewed domain dependency wiring:
.venv/bin/python -m backend.stillhere.agent_extensions.live_smoke \
  --mode no-car --run-live --env-file .env.local
```

Omit `--env-file` when configuration is already in the user's process environment.
`--mode all` runs all four proofs and fails if any gate fails. Existing smoke
delegation is proposed as `agent.smoke --extensions finance` (or applications,
outputs, no-car); the dedicated commands above make genuine LIVE intent explicit.

Each mode creates a disposable SQLite database/session and synthetic case. It
constructs `StrandsBedrockProvider` with no model override and permits no scripted
model option. Limits per mode: 60 seconds, ten model turns, twelve tools, 1,024
tokens per response, 120,000 total tokens, 48,000 context/result characters;
Bedrock retains the existing bounded timeouts/retry policy. `all` has four fixed
modes, no autonomous loop/retry. A failure exits nonzero and retains pending status.

Mandatory assertions are executable, not model-judged:

- **Finance:** actual calls to update, calculate, scenario set/compare, read and
  structured-reply tools; one saved 1,200-cent expense; 28,800 actual cash;
  28,800 baseline versus 33,800 hypothetical scenario ending position; saved
  reply contains those grounded tool-derived values and hypothetical label.
- **Applications:** actual preparation/update/structured calls; saved matching
  provisional application; explicit submitted user report; no agency outcome or
  money creation; saved official URL and unknown/no-external-submission labels.
- **Outputs:** actual calculation/publication/structured calls; saved descriptor
  and output metadata, 30,000-cent grounded projected reply, one optional question.
- **No car:** actual action-backed scenario/compare/application/dashboard/reply
  calls; dated null cost persists as incomplete with null ending position, online
  provisional route and blocked office context; sourced reply/questions, no
  inferred fee, task completion, approval, consent, location or outreach.
- **Every mode:** complete saved turn; all required NEW tool names have successful
  real invocations; no rejected/failed/clarification mutation can count as success;
  unchanged published policy; reopened CaseService reads the exact saved snapshot;
  replay is `already_applied`, cannot reclaim a completed run, makes no further
  tools/events/simulated effects, and leaves the snapshot unchanged.

Output is fixed-label JSON containing only allowlisted mode/status/code, Boolean
assertions and counts. It never prints tokens, case IDs, model IDs, provider error
text, prompts, tool arguments/results or assistant text. Logging is disabled in
this CLI so provider exception traces do not become diagnostics. Failures emit
pending plus a fixed assertion label or `live_proof_unavailable`. Return only the
sanitized JSON evidence and exit result to the owner. A text-only response,
scripted model, historical planner smoke or model refusal cannot pass these gates.
Direct authorization tests separately establish denied operator/consent escalation.

Live status remains pending until genuine successful output from these commands
arrives. No deployment, Plaid, live welfare outreach or frontend work is included.
