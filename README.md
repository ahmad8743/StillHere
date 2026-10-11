# StillHere

P1's implemented foundation is **C01: private household cases and intake persistence**. It creates a recovery file with optional initial selections, resumes it, and applies auditable `fact.correct` and `intake.submit` commands. The product scope lives in [the specification](docs/project-specification.md); ownership and progress live in [the contracts](docs/contracts-and-progress.md).

The confirmed deployment direction is **Akamai Cloud for the entire application**, with the **Strands Agents SDK** running in the backend and calling an **AWS Bedrock model**. The uncommitted first C02 attempt was rolled back when this direction changed; C02 is planned, and the case/intake contracts remain at `0.1`. See the [architecture and reference handoff](docs/infrastructure-direction.md).

## Run and verify

Requires Python 3.11+ with the system IANA time-zone database. No packages, provider credentials, or network downloads are needed. Run from the repository root:

```sh
python3 -m backend.stillhere.server --db var/cases.sqlite3 --port 8000
```

The service listens on `127.0.0.1`. SQLite data survives restarts. This is a local synthetic-household prototype; deployment, TLS, session recovery/expiry, and operator provisioning remain later work.

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

The 26 tests use temporary databases. The HTTP checks require permission to bind an ephemeral loopback port. They cover the documented empty snapshot, restart/resume, isolation, duplicate events, conflicting writes, concurrent writers, audit times, schema validation, unauthorized channels, pending calculations, and atomic rollback after storage failure, plus intake skips/merges and upgrades from the first slice's database.

## HTTP boundary for P2

Use `contracts/case-service.schema.json` (`$defs`) for client types and mocks. All JSON requests and responses carry `contract_version: "0.1"`. Read requests carry `X-Contract-Version: 0.1`. Case routes also require `Authorization: Bearer <session_token>`; a case ID alone grants no access.

| Operation | Request | Response |
| --- | --- | --- |
| `POST /v1/sessions` | `SessionRequest`: `{"contract_version":"0.1"}` | HTTP 201, `SessionResult`; server issues a household bearer token |
| `POST /v1/cases` | `CreateCaseRequest`: version, stable `event_id`, IANA `time_zone`; optional `intake` and `occurred_at` | HTTP 200, `CommandResult` containing the complete snapshot |
| `GET /v1/cases/{case_id}` | Bearer token and contract header | HTTP 200, `CaseSnapshot` |
| `POST /v1/commands` | `CommandEnvelope`; `fact.correct` with `FactCorrectionPayload` or `intake.submit` with `IntakeSelections` | `CommandResult` |
| `GET /health` | None | Version, status, and implemented command types |

HTTP status codes: `200` applied/already applied, `409` version conflict, `400` rejected input/unsupported command, `401` invalid session, `403` forbidden authority channel, `404` inaccessible or absent case, and `503` unavailable storage. A wrong household sees the same error for an existing case and a missing case. Malformed transport, unusable/missing event IDs, and read/session errors use `AccessError`; well-formed case/command submissions use `CommandResult`, including rejection. Responses disable HTTP caching. POST bodies must use `application/json`, unique keys, finite numbers, and a body no larger than 64 KiB.

For example, a correction's payload is:

```json
{
  "fact_key": "mobility",
  "value": "no_car",
  "observed_at": "2026-10-10T15:00:00Z"
}
```

The service supplies `state: "user_reported"` and empty `source_ids`. A `null` value records an explicit correction back to `unknown`. Omitted facts remain unknown. Fact keys are lowercase identifiers; values are JSON data. Facts never confer roles, consent, confirmed support, or authoritative ledger changes. Current location, damaged residence, and issuing jurisdiction should use separate keys; setting a location fact does not share it.

This smoke walkthrough calls the real running service and prints no bearer token. It keeps the token in memory only:

```python
import json
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8000"

def call(path, body=None, token=None):
    headers = {"Content-Type": "application/json", "X-Contract-Version": "0.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request(base + path, data=data, headers=headers)) as response:
        return json.load(response)

token = call("/v1/sessions", {"contract_version": "0.1"})["session_token"]
created = call("/v1/cases", {
    "contract_version": "0.1", "event_id": "demo_create", "time_zone": "America/Chicago"
}, token)
case = created["case_snapshot"]
command = {
    "contract_version": "0.1", "case_id": case["case_id"], "event_id": "demo_mobility",
    "expected_case_version": 1, "occurred_at": "2026-10-10T15:00:00Z",
    "channel": "dashboard", "type": "fact.correct",
    "payload": {"fact_key": "mobility", "value": "no_car", "observed_at": "2026-10-10T15:00:00Z"}
}
print(call("/v1/commands", command, token)["status"])  # applied
print(call("/v1/commands", command, token)["status"])  # already_applied
print(call("/v1/cases/" + case["case_id"], token=token)["facts"])
```

## Typed intake for the UI and agent

Use the same `IntakeSelections` object as creation's optional `intake` field or an `intake.submit` command's `payload`. Every selection is optional; `{}` is a valid skipped intake. The schema contains the exact vocabulary:

| Field | Accepted values |
| --- | --- |
| `help_urgency` | `urgent_safety`, `essentials_today`, `recovery_steps`, `unsure`, or `null` |
| `crisis_type` | `flood`, `storm_hurricane`, `wildfire`, `earthquake`, `other`, `unsure`, or `null` |
| `needs` | Unique array of `shelter`, `food_water`, `health_support`, `transport`, `lost_documents`, `aid_applications`, `managing_money`; `["unsure"]` alone, `[]`, or `null` also allowed |
| `household_group` | Unique array of `children_with_me`, `other_adults_with_me`, `helping_someone_else`; `["just_me"]` alone, `[]`, or `null` also allowed |
| `current_location` | `null` or an object with `place` (nonblank entered text) and/or `postal_code` (five digits or ZIP+4) |

For example, a command payload can be:

```json
{
  "help_urgency": "essentials_today",
  "crisis_type": "flood",
  "household_group": ["children_with_me"],
  "needs": ["shelter", "food_water"],
  "current_location": {"place": "Demo City, IL", "postal_code": "60601"}
}
```

The backend creates corresponding user-reported facts. `needs` becomes the `requested_needs` fact, plus one `IntakeNeed` record per selected kind with a stable case-scoped opaque ID and `state: "unknown"`. Selection does not establish a need's coverage or service availability. Re-reporting a kind keeps its ID and coverage state and refreshes its reported urgency using the current valid help-urgency fact, or `unknown`. Unselected need records remain unchanged.

Missing fields preserve existing answers. Explicit `null`, `unsure`, and empty selections set the corresponding fact to unknown without deleting earlier needs. Partial submissions retain unrelated facts, completed work, money, and consent. Household groups do not imply exact headcounts. Current location remains a reported place; it is not geocoded or copied to damaged residence, issuing jurisdiction, or shared location.

Command `occurred_at` supplies intake observation time. Creation can supply an optional `occurred_at`; otherwise observation time is the server receipt time. Creation plus intake commits atomically at case version 1. Later accepted intake commands increment the version once, including a completely skipped submission. Extra intake fields are rejected; additional interpreted facts still use the existing flexible `fact.correct` path.

This slice persists intake. Source retrieval, urgent referrals, follow-up questions, and planning remain future C02/C04/C05 behavior; resources stay honestly labeled `not_requested`.

## P2 browser prototype

Open `frontend/index.html` in a browser. The P2 prototype's synthetic CaseSnapshot fixture is in `frontend/fixtures.js`; `frontend/mock-service.js` provides a browser-local adapter for `readCase`, `intake.submit`, and `fact.correct`; and `frontend/finance-engine.js` calculates the four 14-day examples from integer-cent ledger data. Finance scenarios change the displayed forecast without changing the baseline ledger. The finance engine also exports a pure expense/receipt update function with replay protection and commitment/aid matching, plus a forecast contract for up to three hypothetical scenarios and three costed action alternatives. Unknown action costs make that comparison incomplete instead of being treated as zero. Updates are not yet persisted or exposed as editable controls on the finance page. All values are synthetic. The case adapter does not call the running HTTP service, and it intentionally rejects unsupported commands. The recovery UI sends typed incident, safety, need, opted-in city, and access-barrier facts to the mock case. People can skip the needs/barriers questions, edit either answer from the next-steps card, and resume the locally saved conversation with **Continue**. A local-storage failure is shown in the chat footer with a retry action. Transcript turns and chat progress remain in separate UI demo state because the P1 conversation/agent command is not implemented yet; the browser mock does not demonstrate queued/running/complete/failed agent turns.

Run `npm ci` once, then `npm test` from the repository root (Node.js 18+). The 35 checks cover all four specification forecasts, duplicate handling, actual/planned expense reconciliation, confirmed support and restricted funds, record-update conflicts, receipt-link preservation, and schema validation in Node and the browser. `npm test` also checks that the generated validator matches its source schema. The actual test files are under `tests/frontend/`; there is no `tests/frontend.test.cjs`.

The engine supports `record_transfer`, `reverse_event`, `reverse_record_update`, `set_source_access`, `refresh_balance`, `upsert_money_source`, `upsert_commitment`, `upsert_aid`, and `upsert_support` as well as expense/receipt entries. It exports `apply_financial_update` and `forecast_finances` for a future P1 wrapper, with camelCase aliases retained for the browser. Every proposed update is checked against `contracts/finance-update.schema.json` before domain checks. AJV is a development dependency used to generate `frontend/finance-validation.js`; the browser and Node runtime need no installed third-party packages. After changing the schema or generator, run `npm run build:finance-contract` and commit the generated file with its source. These pure operations return a proposed ledger; the current case adapter still rejects `finance.update`.

See [the P2 finance handoff](docs/p2-finance-handoff.md) for command mapping, proposed schemas, supported operations, and remaining C08 work.

The mock case snapshot is stored under `stillhere.p2.mock-case.v1` in browser local storage. To restore its initial fixture, run `StillHereMockService.reset()` in the browser console. This resets only the mock case, not the separate chat demo state.

## Integration rules

- P1 code lives in `backend/stillhere/`; shared definitions live in `contracts/`. P2's browser prototype, first synthetic CaseSnapshot fixture, browser-local mock adapter, and deterministic finance forecast live in `frontend/`. Remaining F01–F07 fixtures and P2 features are still pending. Synthetic values in `tests/` are C01 verification data.
- Creation retries are keyed by the authenticated session plus creation `event_id`. They return the original case and its latest snapshot. The fingerprint includes optional intake/occurrence fields; preserve the complete request on retry.
- Commands are keyed by `(case_id, event_id)`. Authorization happens before event lookup; duplicate resolution happens before the version check. The logical fingerprint includes all envelope fields except `expected_case_version`. Preserve the original channel, occurrence time, and payload on retry. An altered fact/value needs a new ID.
- A valid version-conflicting command reserves its logical identity without mutating the case. After explicit reconciliation, the same intent can retry with an updated expected version. Conflicts are never automatically rebased. Replaying an accepted command returns its original `applied_case_version` and the latest authorized snapshot.
- Snapshots and accepted audit events commit in one SQLite transaction. New audit entries retain the whole previous case alongside the existing prior-fact field, original observation/occurrence time, first receipt time, and application receipt time. An automatic additive migration preserves existing databases, sessions, and accepted-event retries; historical entries retain their original prior-fact audit and have no reconstructed whole-case history. Only token digests are stored; request bodies/tokens are not logged.
- `commands.py` owns deterministic domain handlers and their payload-schema mapping. The service retains authorization, idempotency, concurrency, and persistence for every registered command. Case creation reuses the same intake transformation. Add future validated handlers here instead of duplicating the write path.
- Corrections and intake submissions conservatively mark existing plan/finance outputs `pending`, preserving completed actions and the last calculations. The additive `pending_input_case_version` identifies the new work; finance `input_case_version` still identifies the retained calculation. Render retained results as pending/stale. This slice does not run a planner or forecast.
- The snapshot schema fixes top-level sections and basic types. Populated source, action, financial, check-in, and other domain records remain to be defined by their owners. The descriptor schema validates kind/shape; record-reference validation belongs to the future publisher. The local validator implements only the schema vocabulary currently used; update it when introducing schema keywords.
- Household sessions accept `chat`, `dashboard`, and `text_simulator`; they cannot acquire operator/system authority by selecting a channel or supplying a role. All other baseline command types return `unsupported_command` until their handlers exist. Keep P2 mocks labeled and separate from real endpoint capability.

The full contract freeze still requires P2 review, remaining domain schemas, fixtures, and the Strands/Bedrock proof. C02–C15 and deployment are not implemented by this slice. The next P1 slice is a bounded Strands/Bedrock tool-call proof using this case service. Its [planned boundary and tool-extension rules](docs/contracts-and-progress.md#c02-first-slice-and-tool-extensions--planned) limit the first tools to case reading and fact correction, with separate adapters registered through an allowlist. Strands can later call `CaseService` methods through validated tools using an authenticated context; no model text supplies an authorization scope.

For local reset, stop the server and remove `var/cases.sqlite3` and any matching `-wal`/`-shm` files. This erases synthetic cases, audit events, and sessions together. The database, `.env`/`.env.*` credential files, and `.references/` directory are ignored by Git; blank `.env.example` templates may be tracked. New databases use private file permissions. Any future browser persistence needs the specified opt-in/erase controls.
