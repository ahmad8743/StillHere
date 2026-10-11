# C04 official sources and manual knowledge review

Updated October 11, 2026. **All five bounded C04 implementation slices are
READY_FOR_INTEGRATION.** The three newest slices add official fetching, separate
candidate/discrepancy submission, and local manual publication with immutable
history. Offline validation passes. The user-run live knowledge smoke passes its
source-failure/discrepancy/reply/replay branch at 13.569 seconds. Successful
national USAGov fetching and the strict model/reply/replay path are now verified
by user-run proofs; Colorado live candidate extraction remains pending. This is a
bounded Colorado reference, with partial policy coverage and unknown household
eligibility. Keep Claude Sonnet 4.5. C09 remains outside this chat's work.

## Enable the tools

`STILLHERE_AGENT_ENABLE_OFFICIAL_SOURCES=true` adds `fetch_official_source`.
`STILLHERE_AGENT_ENABLE_RULE_REVIEW=true` adds that required fetch tool plus
`propose_rule_candidate` and `report_rule_discrepancy`. Both default to false.
These flags do not enable intake, incidents, referrals or rule lookup; each
retains its independent option. Publication and queue administration are absent
from the household tool registry and HTTP routes.

The fetch tool accepts only `source_id`. Five approved source IDs map to public
production government pages. The national USAGov source is fetch-only; Colorado
candidate/discrepancy tools retain their four DMV source IDs.

| Source ID | Official page |
| --- | --- |
| `source_usagov_lost_documents` | [USAGov lost-ID guidance](https://www.usa.gov/replace-vital-documents) — national guidance, not Colorado policy evidence |
| `source_rule_co_replacement` | [Replace a lost, stolen or destroyed credential](https://dmv.colorado.gov/replace-your-lost-stolen-or-destroyed-driver-license/permit/cdl/id) |
| `source_rule_co_renewal` | [Renew a Colorado credential](https://dmv.colorado.gov/renew-your-colorado-driver-license-permit-or-id-card) |
| `source_rule_co_documents` | [Documents](https://dmv.colorado.gov/documents) |
| `source_rule_co_exceptions` | [Exceptions for US citizens and permanent residents](https://dmv.colorado.gov/applicants-who-are-us-citizens-and-permanent-residents) |

Model arguments cannot choose a URL, credentials, household identity or role.
Requests use HTTPS without application authentication, cookies or environment
proxy configuration. Socket timeouts are at most six seconds, with agent-deadline checks around
reads. Other limits are two redirects confined to the same registered path, 256 KiB of raw input and 6,000
characters of extracted text. HTML/text media types and UTF-8 are checked;
scripts, forms and navigation are excluded. The receipt records the actual
retrieval time, content hash, 24-hour expiry and `review_state: unreviewed`.
Fetched text supplies evidence; it cannot instruct the agent or publish policy.

A failed request returns `unavailable`. Any seeded/cached fallback retains its
original provenance and retrieval time; it never becomes a successful live
fetch. The in-memory cache is bounded by the five registered sources. The new
USAGov source has no seeded fallback. Host approval is limited to `dmv.colorado.gov`
and `www.usa.gov`; each source still requires its own exact registered path.

## Separate public submissions

Ten additive shared definitions cover fetch arguments/receipts/results,
candidate/discrepancy arguments, review records, submission results and manual
publication requests/results. Contract `0.1` remains unchanged. Published
rule/source data modes additionally support reviewed `cached` versions, and
source attribution can carry `content_sha256`. P2 boundary review remains a gate.

Both submission tools accept a known program, its current published base
version and a registered source ID. The backend requires an explicit matching
`document_issuing_state` and a receipt fetched in the same agent turn.
Candidates use allowlisted requirement keys, an AND/OR relationship and public
text offsets. Content reports use an allowlisted discrepancy reason and text
offsets. Evidence spans are nonblank and at most 800 characters, selected by
the backend from public fetched text. There is no free-text household payload.
Extraction/content reports require fresh live evidence. A failed request permits
only a `source_unavailable` discrepancy without a claimed live excerpt.

`CaseService` owns every durable write. Public candidate records, private
case/parent-effect links, reviewed catalogs, immutable versions and manual
review audits use separate tables in the same protected SQLite database.
Candidate and effect-link insertion is atomic. Public review projections exclude
case/session/parent IDs, household facts, document numbers and finance. The
private link stays private; separate tables do not constitute a separate database
access boundary.

Submission leaves the household snapshot/version, domains, published catalog
and case audit unchanged. Identical submissions within a turn return the same
candidate; case-version conflicts block further writes. Ownership, run leases
and deadlines are checked before commit. Accepted submissions survive later
provider failure; replay of a completed chat returns its saved reply.

## Local manual publication

The CLI uses explicit local OS/database administrator access, represented by
`ManualReviewAuthority`, and an opaque reviewer tag. A household bearer token,
model argument or role string cannot invoke publication. This local boundary
does not implement deployed operator provisioning; that remains C01 work.

For a persistent local service database, a human reviewer can inspect and draft:

```sh
.venv/bin/python -m backend.stillhere.knowledge.manage --db var/cases.sqlite3 --reviewer reviewer_demo list
.venv/bin/python -m backend.stillhere.knowledge.manage --db var/cases.sqlite3 --reviewer reviewer_demo show candidate_ID
.venv/bin/python -m backend.stillhere.knowledge.manage --db var/cases.sqlite3 --reviewer reviewer_demo draft candidate_ID > /tmp/public-review.json
```

The reviewer checks the public evidence, scope, requirements, alternatives and
source attribution, edits the draft, selects a new immutable version and review
event ID, then explicitly applies it:

```sh
.venv/bin/python -m backend.stillhere.knowledge.manage --db var/cases.sqlite3 --reviewer reviewer_demo apply /tmp/public-review.json
```

Drafting only outputs editable public JSON; `EDIT_` placeholders cannot publish.
Review input must be a bounded public JSON document with unique keys and finite
values; credential paths and symlink inputs are rejected. Neither CLI command
loads credential files or invokes a model. The disposable agent smoke database
is deleted after the run; use the offline workflow below to exercise publication.

Publication checks candidate/catalog versions, current base policy, fresh live
evidence, exact source hash/time, official identities, current human review
metadata and graph validity. Stale/failed evidence, cycles, altered attribution
used by another active program and reuse of an immutable version are rejected.
The new active catalog, archived versions, candidate decision and manual audit
commit atomically. Replaying an accepted review returns its original outcome;
changed intent requires a new event ID. Rejection/resolution changes no policy.
Rule lookup reads the active catalog or an explicitly requested archived version;
it never reads pending candidates or silently chooses the newest conflicting rule.

## Bounded document alternatives

Seed catalog `2026-10-10.rules.2` retains `co_state_id_replacement` version
`2026-10-10.1` and its original source review times. A separate program,
`co_state_id_proof_options` version `2026-10-10.1`, contains partial standard
proof and exceptions paths. The documents/exceptions pages were reviewed at
`2026-10-11T03:53:07Z`, with a 30-day maintenance budget.

The standard path requires confirmation that the checklist applies. It includes
selected identity alternatives (passport, or birth certificate plus another
qualifying document), SSN reporting/proof alternatives and two qualifying address
proofs. The exceptions path requires DMV confirmation and its incomplete initial
application process; permanent-resident lawful-presence restrictions remain
explicit. These first-application/applicant-group rules are not automatically
applied to renewal. Full proof lists, individual applicability, name/translation
conditions, fees and unstated policy effective dates remain unknown.
`coverage_complete` stays false; a reviewed graph does not establish eligibility.

Colorado is the example jurisdiction. Current C04 smoke fixtures use synthetic
Denver needs or a reported Colorado document issuer; no specific wildfire,
flood or named disaster is asserted.

## Working live-fetch example — verified

The user's required successful new-information example passed on October 11, 2026,
clearing this gate before C05.
The Colorado renewal probe returned HTTP 403. Its denial is retained as a source
access failure; the new example uses USAGov's national lost-ID page rather than
changing the DMV request to evade that refusal. The public USAGov page was read
successfully through the web reader. Direct backend requests still hit DNS failure
in the Codex environment; the user's terminal/backend and live model proofs
succeeded separately.

First run the credential-free example:

```sh
.venv/bin/python -m backend.stillhere.knowledge.fetch_smoke
```

A successful result must show `state: available`, `live_fetch_passed: true` and
`data_mode: live`, a current retrieval timestamp, content hash, official URL and
an actual short guidance excerpt from the response. This command uses the same
bounded transport, validates the receipt and requires the expected useful text.
It writes no household data and invokes no model. An unavailable/cached/seeded
result or a 200 response without the relevant guidance fails. To inspect failure
categories/status without printing public text:

```sh
.venv/bin/python -m backend.stillhere.knowledge.check_source --source-id source_usagov_lost_documents
```

Then the user runs the strict Sonnet proof:

```sh
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --fetch
```

It enables official fetching and disables the review tool group for a disposable
synthetic case. Sonnet must explicitly call `fetch_official_source` for the national
source, receive fresh useful text, and save a reply quoting the returned short
state-ID contact sentence with its official URL. The smoke checks unchanged
household domains/published rules and replay without refetch. It prints the
backend retrieval timestamp, source URL and fetched excerpt after success.
A missing/unavailable source, wrong page text, unsupported reply or domain change
exits nonzero; failure handling cannot pass this mode. Safe pass logs identify
`mode: fetch` and `retrieval_state: available`, without response text in the log.
This proves live public retrieval/use, not Colorado policy extraction/publication.
The earlier `--knowledge` failure-path proof remains separate.

No credentials were read by Codex, and Codex does not run the Bedrock proof.
The user-run credential-free receipt records successful live retrieval at
`2026-10-11T05:16:53.123600Z` (12:16 a.m. October 11 in Chicago), 1,524 extracted
characters, no truncation and `review_state: unreviewed`. Its public content hash
is `64f7a99724de92e8a5e2ed935fbbca14be69b3887d4e12881a86143cb7c56c48`.
The strict model smoke fetched again at `2026-10-11T05:18:02.014708Z`.
The safe log confirms one completed tool call, a completed run and `smoke_passed`
at 13.265 seconds with `mode: fetch` and `retrieval_state: available`. Its
assertions establish fresh useful public text, quoted/cited saved reply,
unchanged household domains/published rules and replay without refetch.

This verifies the requested live-fetch example. It does not approve policy or
verify Colorado candidate extraction. C05 is now IN_PROGRESS with its first
read-only evaluation slice READY_FOR_INTEGRATION; this fetch prerequisite is
satisfied. [Planner handoff](planner-integration.md).

## Validation and remaining user checks

At the C04 fetch-example milestone, all 203 non-HTTP checks passed, including 24 referral, 28 rule,
34 knowledge, six diagnostic, ten strict fetch-example and 17 real pinned-Strands
SDK checks. The 67 focused fetch/knowledge/diagnostic/SDK checks also pass. Evidence
covers malformed/oversized/late sources, hostile arguments, fallback provenance,
privacy, rollback, replay, household isolation, manual authority, concurrent
reviews, immutable history, restart and the live-smoke assertions through
synthetic transports. The credential-free end-to-end workflow also passed, with an additional
user-reported terminal pass.
All publication tests used temporary databases and synthetic evidence.

That milestone discovered 208 checks. The five existing HTTP checks hit this
host's loopback restriction at the earlier full-suite milestone; all 203 milestone
non-HTTP checks passed. No new HTTP handlers were introduced.
Direct backend public-page requests currently fail DNS resolution here; browser
source review passed separately. The user-run national USAGov backend fetch and
strict model proof now pass; Colorado live candidate extraction is unverified. The earlier user-run rules/resources smokes passed at 14.992/18.535
seconds. The new knowledge safe log confirms two completed tool calls, a
completed run and `smoke_passed` at 13.569 seconds with
`mode: knowledge` and `retrieval_state: unavailable`. This verifies the real-model
failure/fallback and unpublished discrepancy branch, unchanged policy/household
domains, durable reply and replay. Successful national fetching now passes through
the independent `--fetch` proof; Colorado live candidate extraction remains
unverified. The log does not record the fetch failure reason, and the
Codex-host DNS failure cannot establish the cause of this user-run failure.

Run from the repository root:

```sh
# Full local suite, including subsequent C05/finance checks and five HTTP checks
.venv/bin/python -W error::ResourceWarning -m unittest discover -s tests -q

# Disposable, credential-free fetch through manual publication/restart/replay
.venv/bin/python -m backend.stillhere.knowledge.smoke

# Credential-dependent proof: failure branch passed; live extraction still pending
.venv/bin/python -m backend.stillhere.agent.smoke --env-file .env.local --knowledge
```

The `--knowledge` command enables its own tools, creates a disposable synthetic
case, checks pending public submissions, unchanged policy/household domains,
durable reply and replay. It never publishes a rule. Success exits zero and
records `mode: knowledge` with an allowlisted `retrieval_state` in the safe
`var/agent-smoke.jsonl` log. `available` proves live fetching and candidate/report
submission; `unavailable` proves source-failure handling and discrepancy
submission, with successful extraction still pending. Codex does not run the
credential-dependent command or read private configuration.

The successful live-fetch prerequisite is satisfied. C05's first deterministic
read-only evaluation slice is now READY_FOR_INTEGRATION; full C05 remains
IN_PROGRESS for deeper evidence/dependency and cost integration; plan/task
slices are now ready independently. Shared boundary
review and the remaining verification gates are tracked separately. Broader policy coverage,
service capacity, deployed operator access, UI integration and deployment remain
separate work. C04 is ready for integration, not marked integrated or fully
verified against live providers.

## Diagnose an unavailable public source

The previous user-run smoke retained `retrieval_state: unavailable` without the
fetch failure reason, so its historical cause cannot be recovered from that log.
A new standalone command repeats the approved renewal-page request through the
same public transport and prints only safe status/category/count fields:

```sh
.venv/bin/python -m backend.stillhere.knowledge.check_source
```

It loads no environment files, calls no model/AWS service, writes no case data
and prints no page body, URL, headers or exception message. Source selection is
restricted to the existing registry; `--source-id` can select another registered
page. Its cooperative deadline defaults to ten seconds (`--timeout` accepts
1–30); socket timeouts remain at most six seconds. Exit zero means usable text
was extracted; exit one means the diagnostic request failed, with JSON details.

| Safe output | Meaning |
| --- | --- |
| `reason: dns_error` | The requesting environment could not resolve the website's network address. |
| `reason: tls_error` | The HTTPS connection/certificate check failed. Verification remains enabled. |
| `http_status: 403` | The server refused this public request; this alone does not identify its reason. |
| `http_status: 429` | The server rate-limited this request. |
| `reason: timeout` | The request exceeded a socket timeout or cooperative deadline. |
| `http_status: 200`, `code: source_invalid_response` | A response arrived, but its media type, encoding or extracted text failed validation. |
| `state: available` | This request successfully extracted bounded public text; review remains separate. |

Both the standard and requested-access Codex probes returned `dns_error`.
That establishes this environment's current failure, not the cause of the earlier
user-run smoke. The user can run this command in the same terminal to diagnose
their environment without paying for another model invocation.

The user's terminal reproduction returned `source_http_error`, `http_status: 403`
and `reason: http_error` in 0.435 seconds. That request received a server refusal,
distinct from the Codex probes' DNS failures. The status does not establish why
the server refused access, and it cannot recover the earlier smoke's historical
response. Colorado live candidate extraction remains unverified; the national
live fetch now passes. C05 can use
the existing reviewed published seed while this source-access gate stays open.

Six new diagnostic tests cover HTTP status, DNS/TLS/timeout/connection categories,
success counts, invalid content, bounded/approved inputs and CLI exit status,
with private fixture text excluded from output. All 66 focused diagnostic,
knowledge and agent checks passed; these used synthetic transports and temporary
storage. That diagnostic milestone contained 197 checks. The earlier 186 non-HTTP checks remain the previous iteration's evidence.

At the C05 milestone, 28 planner and two additional real-SDK checks pass; the
focused planner/rule/SDK run passes 75. Later shared discovery runs 295 checks:
290 pass, including 57 concurrent finance checks and 19 total real-SDK checks;
the same five HTTP checks hit host-prohibited loopback binding. These totals
supersede the historical 203/208 counts above. C05 consumes only reviewed
published active/exact archived rules, with no fetch, review submission,
publication or household-domain writes. Colorado live extraction remains
unverified; neither the national fetch proof nor household Boolean reports
establish eligibility. The live planner proof is a separate user-run check in
the [C05 handoff](planner-integration.md).

C05 has now added CaseService saved-plan revisions and explicit task reports as
two separate READY_FOR_INTEGRATION slices. Only published rules are consumed;
planning/task effects cannot submit candidates, publish policy or turn household
completion into agency approval. Current validation is 108 focused checks and
325 passing non-HTTP checks among 330 discovered; five existing HTTP checks and
live `--planner`/`--plan` proofs remain pending. See the updated
[C05 handoff](planner-integration.md) for independent flags, compact model summaries,
preserved source/history/freshness and user-run checks.
