# C03 incident context — integration handoff

Updated October 10, 2026. **C03 is READY_FOR_INTEGRATION.** The NWS, USGS and
OpenFEMA adapters, shared schemas, CaseService commit and opt-in Strands tool are
implemented. All three public APIs passed a synthetic live request; populated
records, failures and agent integration are covered by offline fixtures. A live
Sonnet invocation of the new C03 tool remains a separate user-run check. C09 is
outside the current chat's work.

## Enable and exercise the agent tool

No additional credentials are required for the three public incident sources.
Keep the working Sonnet 4.5 Bedrock settings. Set this non-secret option in private
`.env.local`, or supply it in the server's process environment:

```dotenv
STILLHERE_AGENT_ENABLE_INCIDENTS=true
```

The blank `.env.example` includes the option, disabled by default. With it enabled,
the registry adds `get_incident_context` alongside the default read/fact tools.
Its input is `IncidentToolArguments`:

```json
{"location_scope":"current","lookback_days":30}
```

`location_scope` is required (`current` or `damaged`). The default lookback is 30
days, bounded to 1–365. The backend supplies case/session/run authority, current
time, geography and crisis type. The model cannot select coordinates, a case ID,
credentials or a fetch URL through this tool.

Run a live model/tool proof on a disposable synthetic Denver case:

```sh
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --incidents
```

This explicitly enables C03 for the proof, asks the configured model to call the
tool, checks saved context and at least one validated official-source result,
checks the reply, and verifies event replay. It uses the existing safe phase log.
Codex does not run this credentialed command or inspect `.env.local`.

## Geography and source behavior

Use reported structured `current_location` or `damaged_location` facts. Current
location also accepts these additive fields in `IntakeLocation`, while existing
place/postal-only intake remains valid. A synthetic example is:

```json
{
  "place":"Synthetic Denver",
  "latitude":39.7392,
  "longitude":-104.9903,
  "state":"CO",
  "county_fips":"08031"
}
```

Coordinates must be a complete valid pair. County FIPS is a five-digit string
whose state prefix matches the supplied state. [Census geographic codes](https://www.census.gov/library/reference/code-lists/ansi.html).
Place/postal text is not geocoded in this slice. Unknown, conflicting, stale or
invalid location facts remain unknown for lookup; missing geography never becomes
a nationwide search. Retrieval does not enroll a household or populate
`shared_location`.

| Source | Query and normalized context | Missing geography / limits |
| --- | --- | --- |
| NWS | Active actual alerts/updates for a reported point, otherwise a reported state. Retains official text excerpts, instructions, sent/effective/expiry/end times and geographic scope. | Needs coordinates or state. State results have broad relevance, not confirmed household impact. The active endpoint has no `limit` parameter; bytes and retained records are bounded locally. [NWS API](https://www.weather.gov/documentation/services-web-api). |
| USGS | Catalog earthquakes of magnitude 2.5+ within 100 km and the stated time window; retains event/update times, coordinates, magnitude, depth and review label. | Needs coordinates. Historical earthquake occurrence is not a current alert or eligibility decision. [USGS catalog API](https://earthquake.usgs.gov/fdsnws/event/1/). |
| OpenFEMA | Declarations dated within the time window for the reported state and, when supplied, county plus statewide records. Retains incident/declaration dates and nullable IHP/IA/PA/HM program flags. | Needs state. Exact county and broad state relevance remain distinct; statewide records do not establish county program coverage. Household eligibility is always unknown. Current v2 fields checked against the [public endpoint](https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries?%24top=1) and [FEMA's API examples](https://github.com/FEMA/openfema-samples). |

The reported crisis type remains separate from provider classifications. These
queries do not establish comprehensive wildfire, incident, assistance or resource
coverage. A successful empty query does not rule out a disaster or other support.

Each provider returns `available`, `no_match`, `unknown`, or `unavailable`, plus
records, attribution, an official referral, a typed issue and `truncated`. Overall
context can also be `partial`; retained context becomes `stale` after a relevant
case-input change. Do not replace a failed lookup with `no_match`.

Requests use fixed HTTPS official hosts, a public application User-Agent, no
credentials, no inherited proxy configuration, one attempt, at most six seconds
per socket operation and checks a 20-second facade deadline capped by the agent deadline.
A blocked socket finishes cooperatively; responses received after the deadline are discarded.
JSON responses are limited to 1 MiB; malformed JSON, duplicate keys, non-finite
numbers, foreign redirects, malformed records and string-valued program flags
produce typed source failures. At most five records per provider enter context.
Text excerpts are bounded and explicitly marked `text_truncated`; use the record
URL for complete official instructions. Source content remains data for the agent.

Application freshness budgets are five minutes for NWS/USGS and one hour for
OpenFEMA. An alert's expiry/end can shorten that budget. Consumers compare a
successful source's `fresh_until` with current time; the timestamp describes
retrieval freshness, not a guarantee that an old earthquake or declaration is an
active hazard. Unknown/unavailable sources are not treated as fresh positive data.

## Persistence and contract boundary

The additive optional `CaseSnapshot.incident_context` keeps independent `current`
and `damaged` results using `IncidentContext`. Existing empty snapshots remain
valid under contract `0.1`. Each result records input case version, query scope,
window, provider states, records, source IDs, source times and notices. Provider
attribution also appears in the existing `sources` section.

`CaseService.commit_agent_incident_context` alone commits the server-produced
result. It validates the schema/source references and checks ownership, active
run, expected version and current reported query inputs in one transaction.
Context, replaced sources, version and the previous-case audit commit atomically.
Concurrent changes return a conflict and block further writes in that run; late
tools cannot commit. Existing plan/finance outputs are marked pending when present.

An internal `incident.context` event uses a backend-generated child identity from
the parent event and logical query. Repeated calls in a turn reuse its first
retrieved result and commit once. A new message can retrieve again; sources are
replaced within their location scope instead of accumulating copies. Accepted
context remains saved if the model fails afterward. This adds no public command
type, source publishing permission or direct database access for the model.

Location/crisis corrections retain previous records with `state: stale` and
invalidate their freshness. Correction of one location does not invalidate the
other location's context. Joint boundary review remains part of the broader
contract freeze; UI work does not gate this C03 implementation.

## Recorded verification

All 99 offline checks pass, including 28 C03 checks and a real Strands SDK path
using synthetic source transport. Evidence covers populated record normalization,
UTC conversion, county/radius/window relevance, expiry, program unknowns,
truncation, provider failures/referrals, authority, conflicts, run expiry,
restart/replay, separate location contexts, stale inputs and atomic storage rollback.

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q
.venv/bin/python -m backend.stillhere.incidents.smoke
```

The second command calls public APIs using a fixed synthetic Denver example and
never loads environment/credential files. The recorded check at
`2026-10-11T01:12:25.900302Z` (October 10 locally) returned validated `no_match`
from all three APIs with zero records. `var/incident-smoke.json` contains only
synthetic status/count/error-code evidence and is ignored by Git. These live
empty responses verify requests and empty-response handling; populated record
and failure-path evidence is from labeled fixtures. The separate Sonnet/C03
smoke command has not yet been run with credentials.
