# StillHere

P1's first implementation slice is **C01: private household cases**. It creates an empty recovery file, resumes it, and applies auditable `fact.correct` commands. The product scope lives in [the specification](docs/project-specification.md); ownership and progress live in [the contracts](docs/contracts-and-progress.md).

## Run and verify

Requires Python 3.11+ with the system IANA time-zone database. No packages, provider credentials, or network downloads are needed. Run from the repository root:

```sh
python3 -m backend.stillhere.server --db var/cases.sqlite3 --port 8000
```

The service listens on `127.0.0.1`. SQLite data survives restarts. This is a local synthetic-household prototype; deployment, TLS, session recovery/expiry, and operator provisioning remain later work.

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

Tests use temporary databases. The HTTP checks require permission to bind an ephemeral loopback port. They cover the documented empty snapshot, restart/resume, isolation, duplicate events, conflicting writes, concurrent writers, audit times, schema validation, unauthorized channels, pending calculations, and atomic rollback after storage failure.

## HTTP boundary for P2

Use `contracts/case-service.schema.json` (`$defs`) for client types and mocks. All JSON requests and responses carry `contract_version: "0.1"`. Read requests carry `X-Contract-Version: 0.1`. Case routes also require `Authorization: Bearer <session_token>`; a case ID alone grants no access.

| Operation | Request | Response |
| --- | --- | --- |
| `POST /v1/sessions` | `SessionRequest`: `{"contract_version":"0.1"}` | HTTP 201, `SessionResult`; server issues a household bearer token |
| `POST /v1/cases` | `CreateCaseRequest`: version, stable `event_id`, IANA `time_zone` | HTTP 200, `CommandResult` containing the complete snapshot |
| `GET /v1/cases/{case_id}` | Bearer token and contract header | HTTP 200, `CaseSnapshot` |
| `POST /v1/commands` | `CommandEnvelope`; currently `fact.correct` with `FactCorrectionPayload` | `CommandResult` |
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

## Integration rules

- P1 code lives in `backend/stillhere/`; shared definitions live in `contracts/`. P2's frontend, finance module, and F01–F07 mock fixtures remain P2-owned and have no implementation paths yet. Synthetic values in `tests/` are C01 verification data.
- Creation retries are keyed by the authenticated session plus creation `event_id`. They return the original case and its latest snapshot. This slice creates empty cases; optional intake selections and `intake.submit` will be added together later.
- Commands are keyed by `(case_id, event_id)`. Authorization happens before event lookup; duplicate resolution happens before the version check. The logical fingerprint includes all envelope fields except `expected_case_version`. Preserve the original channel, occurrence time, and payload on retry. An altered fact/value needs a new ID.
- A valid version-conflicting command reserves its logical identity without mutating the case. After explicit reconciliation, the same intent can retry with an updated expected version. Conflicts are never automatically rebased. Replaying an accepted command returns its original `applied_case_version` and the latest authorized snapshot.
- Snapshots and accepted audit events commit in one SQLite transaction. The audit retains the previous fact, original observation/occurrence time, first receipt time, and application receipt time. Only token digests are stored; request bodies/tokens are not logged.
- Corrections conservatively mark existing plan/finance outputs `pending`, preserving completed actions and the last calculations. The additive `pending_input_case_version` identifies the new work; finance `input_case_version` still identifies the retained calculation. Render retained results as pending/stale. This slice does not run a planner or forecast.
- The snapshot schema fixes top-level sections and basic types. Populated source, action, financial, check-in, and other domain records remain to be defined by their owners. The descriptor schema validates kind/shape; record-reference validation belongs to the future publisher. The local validator implements only the schema vocabulary currently used; update it when introducing schema keywords.
- Household sessions accept `chat`, `dashboard`, and `text_simulator`; they cannot acquire operator/system authority by selecting a channel or supplying a role. All other baseline command types return `unsupported_command` until their handlers exist. Keep P2 mocks labeled and separate from real endpoint capability.

The full contract freeze still requires P2 review, domain schemas, fixtures, and the Strands/Qwen proof. C02–C15 and deployment are not implemented by this slice. Strands can later call `CaseService` methods through validated tools using an authenticated context; no model text supplies an authorization scope.

For local reset, stop the server and remove `var/cases.sqlite3` and any matching `-wal`/`-shm` files. This erases synthetic cases, audit events, and sessions together. The database and environment files are ignored by Git; new databases use private file permissions. Any future browser persistence needs the specified opt-in/erase controls.
