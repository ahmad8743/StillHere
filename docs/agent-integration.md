# C01-facing agent slice — integration handoff

Updated October 10, 2026. **The C01-facing Strands adapters and bounded C02 runtime
are READY_FOR_INTEGRATION after the user-run live Bedrock proof passed.** The user
selected Claude Sonnet 4.5 as the current working model. The broader C02 component
remains IN_PROGRESS for later tools and output contracts. C01 remains IN_PROGRESS
for its other domain handlers and operator provisioning. The public contract
remains `0.1`; the populated conversation definitions are additive and await P2
boundary review.

## Implemented tools and extension boundary

| Tool | Default | Service / schema |
| --- | --- | --- |
| `read_case` | Enabled | Authorized `CaseService.read_case`; empty arguments; `CaseSnapshot` result |
| `correct_fact` | Enabled | `fact.correct`; `FactCorrectionPayload` arguments; `CommandResult` result |
| `submit_intake` | Opt-in | `intake.submit`; `SubmitIntakeToolArguments` with `selections`; `CommandResult` result |
| `get_incident_context` | Opt-in | C03 public source facade and CaseService internal commit; `IncidentToolArguments`; `CommandResult` result |

Set `STILLHERE_AGENT_ENABLE_INTAKE=true` when integrating the intake adapter. Its
shared selection vocabulary, unknown coverage, provenance, and consent behavior
are the existing C01 behavior. Set `STILLHERE_AGENT_ENABLE_INCIDENTS=true` for
C03 NWS/USGS/OpenFEMA context; no new source credentials are needed. The
[C03 handoff](incident-integration.md) records geography, freshness, persistence
and live-source evidence. Other inventory tools remain unregistered. C09 is
outside the current chat's work.

`backend/stillhere/agent/registry.py` records each name, description, input/result
schema, callable, role, access classification, component, and budget cost. Add a
domain adapter, agreed shared definitions, registry entry, and focused validation,
access, failure, and replay checks before enabling another tool. Provider schemas
inline shared references; the application validates against the original schema.
The wrapper validates the original `ToolContext.tool_use` input so SDK-inserted
optional `None` defaults cannot change the application's schema/default behavior.
Strict Bedrock tool-schema mode is not enabled. The tested SDK override is named
`inputSchema`, despite the earlier inventory's proposed `input_schema` spelling.
[Strands custom tool API](https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/).

The backend supplies session/case/turn/run context through `ToolContext` invocation
state. It never places the bearer token or AWS credentials in the prompt. Model
arguments cannot select case, session, role, channel, or event identity. A hook
checks raw arguments before SDK signature validation can discard extra fields.
Tool calls are serialized and pass through the normal command service.

## Run locally and configure Bedrock

The case API and deterministic tests still run with Python 3.11+ and the standard
library. Install the optional pinned dependencies for the real agent:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-agent.txt
```

Keep virtual-environment package files local. In a synced macOS Documents checkout,
cloud-offloaded (`dataless`) dependency files can stall Python imports before any
AWS call. On this machine `.venv` links to a local environment under
`~/Library/Caches/StillHere/agent-venv-20261010`; the previous environment is
preserved as `.venv.cloud-backup`. Both the link and backup are ignored by Git.
The usual `.venv/bin/python` commands continue to work. If that cache is removed,
recreate it and reinstall `backend/requirements-agent.txt` before running the agent.

Fill the private `.env.local` created beside `.env.example`. Set `AWS_REGION` and
`STILLHERE_BEDROCK_MODEL_ID` to an accessible tool-capable model or inference-profile
ID. Use the AWS credential chain (`AWS_PROFILE`/role credentials), or supply local
`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and, for temporary credentials,
`AWS_SESSION_TOKEN`. Leave the unused credential fields blank. The account needs
permission to invoke the selected Bedrock model. No Akamai credentials are needed
for this local slice. [Bedrock configuration](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

```sh
.venv/bin/python -m backend.stillhere.server --db var/cases.sqlite3 --port 8000 --env-file .env.local
```

Only the explicit `--env-file` option loads a credential file. Nonblank existing
environment values take precedence, and blank template fields do not mask the
AWS credential chain. Model and region have no implicit defaults. Without
configuration, chat messages are accepted durably and their assistant turn fails
with `agent_not_configured`; the deterministic case commands remain available.

The user can verify the live provider without using existing household data:

```sh
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local
```

This uses a disposable synthetic case, asks the real model to read/correct a fact,
checks the saved reply and correction, and verifies message replay. It prints
only a safe pass/failure summary. **The confirmed default-path user-run log records two tool calls
and `smoke_passed` at 6.072 seconds.** An earlier run also passed at 2.291 seconds.
The user confirmed Claude Sonnet 4.5 as the current working choice; logs omit
model IDs, so this attribution comes from the user's report. The proof covers
the default read/fact path, durable reply, and event replay; it does not verify
opt-in intake, later domain tools, UI integration, or deployed behavior.

A subsequent user-run log records one completed tool call and `smoke_passed` at
18.681 seconds. The phase log omits the smoke mode and model ID; attribution to
the default or `--incidents` proof requires its terminal summary.

If the smoke test reports `agent_not_configured`, it has not attempted AWS
authentication: `AWS_REGION` or `STILLHERE_BEDROCK_MODEL_ID` is missing. The next
line lists the missing setting names without printing their values. Both fields
must be supplied explicitly, even when using an AWS profile. An empty or
whitespace-only shell variable does not mask a filled field in `--env-file`;
nonblank shell values continue to take precedence.

Keep the working Sonnet 4.5 model/profile ID in `STILLHERE_BEDROCK_MODEL_ID`.
The user previously confirmed source region `us-east-2`. The adapter uses Bedrock
Runtime's Converse API with explicit configuration; it does not switch models or
fall back automatically. The exact configured ID remains private and was not
read by Codex. Nonblank process environment values take precedence over
`--env-file`, so retain the same working configuration for subsequent runs.

The smoke command appends phase timings and allowlisted error codes to
`var/agent-smoke.jsonl` (already excluded from Git). Override it with `--log-file`.
The log never includes credential values, model/profile IDs, prompts, case content,
exception messages, or raw AWS responses. Codex can read this safe log after the
user runs the credentialed command. `sdk_import_started` without
`sdk_import_complete` locates a local dependency-import stall;
`bedrock_client_started` without `bedrock_client_ready` locates client setup;
`model_invocation_started` locates inference. AWS client failures record a known
error code such as `AccessDeniedException` or `ValidationException`. An owning
runtime's timeout is recorded as `agent_timeout`; abandoned expired runs still
use `agent_interrupted`, and no expired run can commit a tool effect or late reply.
Generated AWS exception subclasses are normalized to `ClientError`. Diagnostics
follow up to eight linked cause/context exceptions to recover an AWS code when
Strands wraps it; raw exception text, notes and request state remain excluded.
For access/validation failures, diagnostics now match a bounded AWS error message
against fixed phrases and retain only an allowlisted `reason`, such as
`model_identifier_invalid`, `inference_profile_required`,
`temperature_unsupported`, `operation_not_allowed`, or
`account_model_access_denied`. Unknown or oversized messages produce
`unclassified`. No message fragments, identifiers or request values enter the log.
These labels identify a service phrase; they do not establish an account's plan
or prove that other access checks have passed.
Resource-not-found failures are also classified; the documented missing
Anthropic use-case phrase or `FTUFormNotFilled` code produces
`anthropic_use_case_required`. The smoke terminal now prints the current run's
sanitized provider code and reason alongside its application failure summary.
It does not read prior log entries or print exception text.

Earlier troubleshooting logs recorded account access denials, a missing
inference-profile requirement, and missing Anthropic use-case details. Those
failures are historical; they no longer block the working model's bounded slice.
The local dependency-import timeout is also resolved. A credential-free real-SDK
transport check validates the adapter's Converse request shape against Botocore:
only `maxTokens` in `inferenceConfig`, two non-strict tools, and no extra model
request fields. The latest live proof supplies separate runtime evidence.

If a future model change encounters access errors, the user can optionally run
read-only access diagnostics with the same explicit credential configuration:

```sh
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --check-access
```

This does not invoke a model, create a case, subscribe to a model, or submit a
use-case form. It resolves an inference profile to its foundation model, checks
Anthropic form presence where applicable, and reports agreement, authorization,
entitlement, and region states. It never decodes or emits the form contents.
Optionally add `--expected-account-id` with the 12-digit account shown in the AWS
console account menu to compare that account with the local credential identity.
Only `MATCH`, `MISMATCH`, or `UNKNOWN` is retained; account IDs and ARNs are not
printed or logged. [AWS caller identity API](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html).

`PENDING` agreement, `NOT_AUTHORIZED`, `NOT_VISIBLE` form, and account `MISMATCH`
help distinguish access problems. `UNKNOWN` can mean missing control-plane
permissions or an unrecognized response, not a proven invocation failure. These
optional reads use `bedrock:GetInferenceProfile`,
`bedrock:GetUseCaseForModelAccess`, and `bedrock:GetFoundationModelAvailability`
as needed, which are separate from runtime invocation permissions. Exit status
zero means the reported control-plane checks passed; live inference remains a
separate proof. The working Sonnet proof does not require this optional checker.
[AWS model-access requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html).

## Chat contract for P2

Submit `conversation.message` to the existing `POST /v1/commands` with the household
bearer token and this payload:

```json
{"message_id":"message_demo_001","text":"I have no car."}
```

The ordinary envelope still supplies version, case/event ID, occurrence time, and
channel. Text must contain a nonblank character and at most 4,000 characters.
`choice_id` is optional and persisted with the user turn; structured choices and
their domain interpretation require a later agreed output schema.

Acceptance atomically appends a completed user turn and a queued assistant turn.
The runtime claims the assistant turn, then saves a complete reply or a failed
turn with a typed `issue`. Render `queued`, `running`, `complete`, and `failed`
from `conversation.turns`; HTTP 200 / `status: applied` means the user command was
accepted, and can accompany a failed assistant turn. The original
`applied_case_version` identifies message acceptance; the returned snapshot can
have later versions from tool writes and turn transitions. Read/resume uses the
existing scoped case endpoint. This slice has no streaming endpoint.

Ordinary calls wait for the current turn up to the configured deadline. A second
message received during a run remains queued and continues in arrival order when
the current run finishes. A lost response is resolved by retrying the exact
original event. A queued turn can dispatch after restart; a running turn's lease
expires into a visible failure on the next chat dispatch/replay. No automatic
model rerun occurs for a complete or failed turn. Send a new message/event to
continue after failure. There is no background startup sweep in this local slice.

## Persistence, conflict, and limits

SQLite retains case snapshots, UI-safe conversation, internal audited state
transitions, and agent-run claims. Run capabilities are stored as digests. One
active run per case is enforced across service instances by a database index.
The agent reconstructs bounded recent completed history from the authorized
case and reads current facts each invocation; raw SDK transcripts, invocation
state, and credentials are not serialized to SDK file sessions. This is
application-owned conversation persistence, without an additional memory store.

Accepted tool effects receive backend-generated identities derived from the
parent event, command type, and logical payload. Repeating an identical mutation
in that turn resolves to the original event. Public commands cannot use
`agent_tool_` or `agent_state_` event prefixes. Tool writes preserve observation
time and the parent's occurrence time; server receipt times remain separate.

Concurrent case edits can conflict with a tool's last read version. After a
conflict, the context blocks further writes even if the model reads again. A new
user message must reconcile the change. Cancellation/provider failure never
undoes an already accepted command. Run validity and command application are
checked in the same transaction; late tools cannot write after completion/expiry.

Defaults are 4 model turns, 6 tool calls, 1,024 output tokens per model call,
12,000 cumulative input/output tokens, 60 seconds per turn, 12 recent conversation
records, and 48,000 context characters. Per-call socket timeouts are 5 seconds to
connect and at most 30 seconds to read; Botocore permits at most two attempts.
SDK retries are disabled. SDK token limits apply between loop iterations and
can overshoot during one model call. The runtime deadline revokes later tools
and exposes failure while a blocked provider call finishes cooperatively.
[Strands lifecycle limits](https://strandsagents.com/docs/user-guide/sdk/agents/lifecycle-controls/).

## Secret-file controls

`.env.local` has private file permissions. `.gitignore` excludes `.env` and
`.env.*`, with `.env.example` as the blank tracked exception. `AGENTS.md` instructs
Codex to avoid credential files and run tests with synthetic settings.

Codex documents filesystem `deny` rules through permission profiles; an ignore
file is not the documented read-access mechanism. The project
`.codex/config.toml` defines the `stillhere` profile denying `.env` and `.env.local`
at the root or nested in any workspace root. Start a new session with that profile
active. The current chat's already-issued sandbox settings cannot be changed by
editing a project file, and managed host policy may override profile selection.
Older `sandbox_mode` settings also take precedence unless the host's managed
profile policy selects profiles. Check the app's active permission profile before
relying on enforcement. [Official Codex permission documentation](https://developers.openai.com/codex/permissions/).

## Verification

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -v
```

The SDK tests use the real pinned Strands loop with a scripted model transport;
they never load `.env.local` or call Bedrock. Without the optional dependency,
those checks explicitly skip. HTTP checks bind only an ephemeral loopback port.
All 99 offline checks pass with the optional dependencies installed. Evidence
covers scoped reads, fact/intake writes, duplicate effects/turns,
concurrent case edits/claims, ordered queued messages, restart/expired-run behavior,
provider/storage failures, bounded execution, raw SDK schema validation, and
credential-free provider configuration, and read-only access diagnostics through
fake clients, and C03 normalization/persistence/SDK integration. Public C03 source
requests pass separately with synthetic geography. The user-run live proof verifies
the current default tool path; a live Sonnet/C03 tool proof and Akamai deployment
remain separate checks. Use `agent.smoke --env-file .env.local --incidents` for the
former; the ordinary smoke command retains its default read/fact proof.
