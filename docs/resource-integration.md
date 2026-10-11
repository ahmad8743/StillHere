# C04 reviewed resource referrals — first-slice handoff

Updated October 11, 2026. **The bounded reviewed-referral slice is
READY_FOR_INTEGRATION with a user-run live model/tool proof. All five bounded
C04 slices are now READY_FOR_INTEGRATION; the new knowledge failure branch passes live, with Colorado live candidate extraction pending.** C03 remains ready
for integration. Keep the working Sonnet 4.5 configuration. C09 is outside this
chat's work. The independent [read-only rule slice](program-rules-integration.md)
is also ready for integration. The [fetch/review handoff](knowledge-review-integration.md) covers the three final slices and remaining verification gates.

## Enable and exercise the tool

Set the non-secret `STILLHERE_AGENT_ENABLE_RESOURCES=true` option in the server
environment or private `.env.local`. The blank `.env.example` defaults it to
false. It independently adds `find_resources` to the allowlist without enabling
intake, incident or rule retrieval. No directory credentials, network request or 211 API
is involved in this slice.

The shared `ResourceToolArguments` accepts only:

```json
{"location_scope":"current"}
```

Scope is required (`current` or `damaged`). Case/session/run authority, reported
needs and geography come from the backend. Model arguments cannot choose a
fetch URL, program rules, coordinates, needs, case identity or role.

The user can run the separate live Sonnet/tool proof:

```sh
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --resources
```

It creates a disposable synthetic Colorado household with shelter/food/transport
needs, requires saved seeded referrals and attribution, checks the completed
reply, and verifies event replay. Its safe phase log excludes case content,
model IDs, exception text and credential values. This command invokes Bedrock;
Codex does not run it or read private configuration. The user-run proof now records `smoke_passed` with `mode: "resources"` at
18.535 seconds, one completed tool call and a completed run. This verifies the
tool/referral/reply/replay path; actual service capacity remains unknown. The default smoke and
`--incidents` and `--rules` modes retain their own proofs; modes are mutually
exclusive. New safe start/pass records include `mode: "resources"`. Older logs
without mode require the terminal summary to identify their proof.

## Catalog, coverage and source review

The chosen demonstration jurisdiction is **Colorado, with synthetic Denver
households**. This first slice covers a Colorado referral route. Partial
Colorado program/document alternatives are available through rule lookup; current/damaged location does not establish a document's
issuing jurisdiction.

`backend/stillhere/resources/catalog.json` is a versioned, read-only public
catalog, separated from household snapshots and future unpublished candidates.
Version `2026-10-10.referrals.1` contains five reviewed routes:

| Route | Coverage and reviewed reference |
| --- | --- |
| Emergency housing | Nationwide [USAGov housing referrals](https://www.usa.gov/emergency-housing) |
| Emergency food | Nationwide [USAGov food referrals](https://www.usa.gov/emergency-food-assistance) |
| Lost documents | Nationwide [USAGov issuing-authority routing](https://www.usa.gov/replace-vital-documents) |
| Disaster assistance | Nationwide [USAGov application and other-help routes](https://www.usa.gov/disaster-assistance), including the published FEMA phone contact |
| Community services | [211 Colorado](https://www.211colorado.org/), including its published 2-1-1 contact and food/housing/transport categories; selected only for reported `CO` |

Public pages were reviewed at `2026-10-11T01:59:58Z` (October 10 locally). This is
source review evidence, not live adapter or service-availability verification.
Each source records its issuer, URL, coverage, supporting section, original
retrieval/review time, nullable precise update time and review expiry. Reviewed
catalog entries are labeled `data_mode: seeded` and
`verification_state: reviewed_referral`. These labels do not publish program
policy. The application maintenance budget is 30 days; expiry makes reviews
stale without deleting the referral. Consumers compare `expires_at` with current
time because saved freshness is evaluated at retrieval/correction time.

Every resource is a **referral** with a URL, nullable phone, coverage and need
categories. Availability and household eligibility remain `unknown`;
requirements are explicitly `unknown` with an empty list, which does not mean no
requirements. Contact providers to confirm service-specific requirements and
capacity. No reservation, contact, dispatch, eligibility decision, resource
consumption or financial saving is recorded.

## Retrieval and persistence

The backend selects referrals from trusted reported `requested_needs` and the
chosen location fact. Corrections to that fact take precedence over retained
historical need records. Unknown/conflicting/stale/invalid needs yield general
routes with an uncertainty notice. Unknown/invalid geography permits nationwide
routes; state-scoped referrals require a valid explicitly reported state.
Place/ZIP text is not geocoded. This lookup does not require a completed profile,
a matching FEMA declaration, or location-sharing consent.

At most five matching candidates and their referenced sources enter a result.
`available` means catalog referrals exist; `no_match` means this completed,
bounded catalog selection had no candidates. Neither establishes live local
coverage. Invalid/unreadable catalogs return `unavailable`, including invalid
records outside the requested geography. Host, source references, coverage and
record identities are checked in addition to structural schemas. The tool
cannot fetch any URL.

`CaseService.commit_agent_resources` checks household ownership, active run,
expected case version and current query inputs in one transaction. It commits
the existing `resources` projection, attribution, case version and previous-case
audit through an internal `resource.search` child event. No public command type
is added. Repeated identical queries in a turn reuse the first result and commit
once; a new message may retrieve again. Source replacement preserves C03 and
other attribution. Accepted referrals remain saved after a model failure.

`resources.search` is an additive optional `ResourceSearchMetadata` field under
contract `0.1`, recording query, input version, lookup time, catalog version,
freshness and truncation. Existing empty/frontend fixture shapes remain valid.
The projection holds the **latest selected scope**; it does not maintain separate
current/damaged resource lists. Sources retain their original review/retrieval
time rather than acquiring the latest lookup time.

A relevant location or requested-needs correction retains the earlier query and
items, marks `search.freshness` and associated sources `stale`, and adds a typed
notice. The other location's correction does not invalidate the selected scope.
Concurrent edits return a conflict and block later writes in that run. Expired
runs and results received after the deadline cannot commit. Storage failures
roll back resources, attribution, version and audit together. A failed catalog
read returns an unavailable `CommandResult` with a typed issue and leaves prior
referrals, their scope and source times intact; it never becomes `no_match`.

## Verification and remaining C04 work

At the C04 completion milestone, 186 non-HTTP offline checks passed, including 24 focused referral
checks, 28 rule checks and 16 real pinned-SDK checks across implemented tools.
The full discovery run collected 191 checks; its five
existing HTTP checks could not bind loopback sockets in this session, including
a rerun requesting loopback access. These same sandbox errors occurred before
C04 changes; current HTTP transport verification remains pending. Evidence covers
unknown/invalid inputs, national/local
selection, source times/expiry, bounded/no-match/failure behavior, authority,
conflicts, stale inputs, replay/restart, storage rollback, preserved incident
attribution, saved effects after provider failure and the resource smoke using a
scripted provider. No credential file or live Bedrock call was used. HTTP checks
use ephemeral loopback sockets.

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q
```

The second C04 slice now supplies read-only versioned Colorado state-ID
renewal references with source-attributed AND/OR online/office alternatives and
opt-in `retrieve_program_rules`; see the [rules handoff](program-rules-integration.md).
The [fetch/review handoff](knowledge-review-integration.md) now supplies bounded
`fetch_official_source`, structured `report_rule_discrepancy` and
`propose_rule_candidate`, and explicit local manual publication. All five bounded
C04 implementation slices are READY_FOR_INTEGRATION. The new live knowledge failure/discrepancy/reply/replay branch passes at
13.569 seconds. National public-source retrieval now passes through the strict `--fetch` proof
at 13.265 seconds; Colorado live candidate extraction remains pending. Full policy
coverage, directory API access/terms, live capacity, UI integration and joint
boundary freeze remain separate gates. Household/model arguments cannot authorize
manual publication. The earlier Sonnet/C04 referral and rule proofs passed
separately at 18.535 and 14.992 seconds.
