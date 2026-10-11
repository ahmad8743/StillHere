# Bounded C07/C12 backend handoff

Date: October 11, 2026. Domain slice: **READY_FOR_INTEGRATION**, with synthetic
verification. Full C07/C12: **integration pending**. Worker registration,
transactional persistence, authenticated operator provisioning, HTTP/UI/agent
adapters, official urgent-resource rendering, and assembled application acceptance
are not implemented here. Live-provider verification: **not applicable to this
simulated domain**; no live welfare outreach is permitted.

The module follows the project specification, contracts-and-progress section 6,
monitoring design, and Strands capability boundaries. Only the new
`backend/stillhere/check_ins/` package, `tests/test_check_ins.py`, this handoff, and
`contracts/parallel/check-ins.schema.json` are owned by this slice. Shared service,
command registry, schema, server, agent, README and progress files are untouched.

## Interfaces

All state and payloads are JSON data. The schema proposal has its own identifier
`urn:stillhere:parallel:check-ins:proposal:1` and domain marker
`check-ins.proposal.1`; neither changes the public `0.1` boundary. Definitions
include every command payload, `State`, `Occurrence`, `Report`, `Attempt`,
`FollowUp`, `SharedLocation`, `TransitionResult`, and `OperatorProjection`.
The small local validator consumes this file and applies additional semantic
checks for consent, chronology, assignment and coordinates. This proposal must
be reviewed and merged/mapped by the integrator before public command enablement.

```python
from backend.stillhere.check_ins import (
    Authority, CheckInProcessor, apply_command, empty_state,
    operator_projection, process_due, validate,
)

empty_state(case_id: str) -> dict
apply_command(
    state: dict, command_type: str, payload: dict, *,
    event_id: str, reported_at: str, received_at: str, caller: Authority,
) -> dict
process_due(state: dict, *, now: str, caller: Authority) -> dict
CheckInProcessor(clock: Callable[[], str]).process(state: dict, *, caller: Authority) -> dict
operator_projection(
    state: dict, *, caller: Authority, now: str, relevant_needs: Iterable[dict] = (),
) -> dict
validate(definition_name: str, value: JSON) -> None
```

`apply_command` and `process_due` return
`{state, effects, changed, duplicate}`. They copy inputs and return proposals;
`changed` does not claim persistence. Duplicate accepted commands return current
detached state, no effects, `changed: false`, `duplicate: true`. Repeated ticks
return no effects and `changed: false` after the first accepted state. Failures
raise `CheckInError(code, field, message)` without altering inputs. C01 maps these
to its existing command-result/issue envelope and never returns private state for
authorization failures.

`State` contains only this domain: case ID, check-in state/occurrences/reports,
active shared location, review requests, accepted event fingerprints, and last
schedule/location control times. It has no ledger, facts, chat or residence.
`check_in.current_occurrence_id` selects the current one-shot schedule; there is
no automatic recurrence. `schedule_id` and due/grace/zone/channel live on each
occurrence. C01 must either store this aggregate privately or map its owned fields
into an approved additive CaseSnapshot schema. Do not replace a whole case with
this domain aggregate. The local event map may move to C01's durable event store
only if equivalent replay protection remains available to this module.

## Proposed payloads and behavior

| Command | Payload | Transition |
| --- | --- | --- |
| `check_in.enroll` | `consent: true`, `follow_up_consent: true`, `due_at`, IANA `time_zone`, `grace_minutes`, `channel`, optional `permitted_need_ids` | Explicit one-shot consent; stable schedule/occurrence; supersede pending old schedule. Already open reviews stay intact. |
| `check_in.reply` | `occurrence_id`, `reply`, optional `next_due_at` | Append report and receipt; answer that occurrence. `check_later` requires a new future time. Other replies may supply an explicit next time too. |
| `check_in.pause` | `intent: pause` or `stop` | Root becomes paused/canceled; scheduling consent inactive; cancel pending scheduled reminders. Existing reviews retain their separately captured scope. |
| `help.request` | `consent: true`, volunteered `message`, optional `occurrence_id` and `permitted_need_ids` | Immediate simulated review without enrollment or a timer; also emit `urgent_help_required`. |
| `location.share` | `consent: true`, `source: user_entered/device_fix`, `observed_at`, `purpose: simulated_follow_up`, `recipients: assigned_handler/case_handlers`, place or coordinates; optional accuracy/expiry | Store one last-shared location, distinct from all residence/fact records. |
| `location.clear` | `{}` | Remove active location completely, including from all subsequent operator views. No historical location copies exist in reviews/effects/event fingerprints. |
| `follow_up.acknowledge` | `request_id` | Assign authenticated caller, record acknowledgment, and set next action. Same owner's repeat acceptance has no additional assignment effect. Another operator cannot steal it. |
| `follow_up.record` | `request_id`, `kind: attempt/outcome`, `simulation: true`, `unresolved_need_ids`, `next_action`, optional `next_due_at`; attempt has channel/result, outcome has outcome enum | Acknowledged owner alone records simulated work. Does not change household needs, condition, consent, schedule or location. |

Attempts use only `in_app`, `text_simulator`, or `phone_simulator`; schedules use
the first two. Delivery state is `simulated`, not a claim of actual delivery.
Operator results are `no_reply`, `reported_contact`, or `unavailable`; outcomes
are `review_complete`, `unable_to_contact`, or `needs_follow_up`. Outcome recording
retains owner/history/unresolved needs. An outcome-recorded request cannot resume
contact implicitly. An explicitly recorded next operator action/date is workflow
metadata; it does not enroll the household or schedule an automatic call.

Every outreach effect, reminder, operator attempt, review, reviewer update and
outcome carries `simulation: true`. No external provider is called. An unanswered
check-in at grace expiry means `condition: unknown`; neither app activity,
delivery, coordinates nor operator outcomes establish welfare. `okay_for_now`
is a timestamped household report, not verified or continuing safety. A newer
occurrence starts unknown even if a prior report was okay.

Old/canceled/paused occurrences may receive a late explicit report. They cannot
replace a newer schedule or resume a paused schedule via `next_due_at`; a new
explicit enrollment is required. Reports remain ordered by original report time
for the latest report/occurrence condition; older offline replies are preserved
without overwriting newer reports. An older `check_later` cannot reschedule after
a newer explicit report. Replies never silently close an existing
review or clear an unmet need, including an outcome-recorded review. They append
an auditable report update and a stable `reviewer_update` effect targeting the
assigned operator when present. Before assignment, updates remain visible for
the next reviewer. An occurrence has one timer-created review identity, and
explicit help coalesces with an open related review. Fresh explicit help after an
outcome creates a new unassigned event-derived request and preserves the prior
owner/outcome. Replies update all related reviewers. An unrelated explicit help
event also has its own request identity.

Pausing/stopping removes permission for future scheduled reminders and overdue
creation, while preserving an open review's captured consent for acknowledgment,
simulated review/contact and outcome. Location permission is independent and
removed with `location.clear`. This command vocabulary does not include revoking
an already submitted review or erasing durable audit history; any such addition
requires a separately reviewed contract. Older unseen offline schedule/location
controls are rejected with `stale_control` when they predate a newer accepted
control; replay of an already accepted share returns no mutation after a clear.

## Trusted authority and operator view

`Authority(case_id, role, subject_id, permissions=frozenset(),
explicit_user_action=False)` is an input contract for a trusted caller. It is not
a session issuer or authentication database. C01 constructs it from verified
household/operator/service context. The household explicit-action attestation
must be tied to this exact command/consent scope; a generic model-turn flag,
model-produced consent Boolean, channel name or payload identity is insufficient.
No payload accepts operator identity, assignment owner, role, or authority.

`AUTHORIZATION_REQUIREMENTS` exposes these enforceable requirements:

| Operation | Role | Permission |
| --- | --- | --- |
| enroll/reply/pause | household, explicit user action | `check_in.write` |
| request help | household, explicit user action | `help.write` |
| share/clear location | household, explicit user action | `location.write` |
| acknowledge/record follow-up | operator | `follow_up.write` |
| due/grace processing | worker | `check_in.process` |
| operator projection | operator | `follow_up.read` |

All operations require exact case scope and an authenticated subject ID.
Authorization precedes event-result lookup. C01 is responsible for session
validation, per-case operator grants, access auditing and version enforcement.
Operators with only read permission cannot mutate reviews; only the acknowledged
owner can record attempts/outcomes. Stale operator reports cannot replace newer
work. No operator tools should enter the household agent registry.

The operator projection returns case reference, simulated receiver status,
consent scope, review trigger/status, volunteered help message, last explicit
report/time, relevant occurrence due/grace/status, simulated attempts, assignment,
report updates, outcomes, unresolved need IDs and next action/date. Need context
requires `needs.read` and both a consented need ID and a trusted same-case input
record. Only ID/kind/state/reported urgency are copied; arbitrary fields and
unknown vocabulary are discarded. No full ledger, residence, identity records,
chat transcript, session tokens, replay map or private facts are accepted/copied.

Location additionally requires `location.read`, explicit sharing permission,
unexpired sharing, and the selected recipient policy. `assigned_handler` exposes
it only to the acknowledged owner; `case_handlers` permits other authenticated
case-scoped operators with that permission. The view labels it last shared,
includes observation/receipt/source/accuracy and age, and always sets
`verified_current_destination: false`. Clearing location leaves no fallback to
damaged residence. Projection access is recomputed from current state on every
read, not cached into review records. C01/UI must invalidate cached projections
when consent/location changes; historical audit access requires its own policy.

## Scheduler and CaseService integration

1. C01 supplies UTC RFC 3339 instants. UI resolves the household's IANA zone and
   DST ambiguity to an explicitly selected UTC due instant; the engine never
   guesses a local time. Due dates must be after server receipt. Grace is bounded
   to 0–10,080 minutes, chosen explicitly, without a universal 24/48-hour policy.
   Report/observation times cannot be future to their authoritative receipt.
2. Register a worker independently of chat/model availability. Inject a callable
   UTC clock through `CheckInProcessor`; it samples once per case processing call.
   Choose polling cadence operationally (e.g. demo-controlled or minute polling);
   no scheduler thread, lease, loop or storage callback is hidden in this package.
   Query current enrolled cases by due/grace time. `now >= due_at` records a due
   reminder; `now >= grace_deadline` creates overdue/unknown review. Due and reminder
   are atomic within a tick, so `reminder_attempted` is the visible post-due state.
3. A delayed tick catches up reminder plus overdue in one transition, with actual
   processing time separate from the agreed reminder time/deadline. This is a
   simulated catch-up, not backdated delivered outreach. Repeated/backward ticks
   do not regress state or duplicate effects. No provider delivery retry policy
   exists in this bounded simulator.
4. In C01, authenticate first, resolve durable replay before checking expected
   version, load current domain, and validate the command envelope. Map
   `occurred_at` to `reported_at`; derive `received_at` once on the server. Preserve
   original IDs/times for offline replay. A changed actor/type/payload/report time
   with the same event ID is rejected; transport version/receipt are excluded from
   the domain fingerprint. Valid conflicts and malformed commands still follow
   C01's event-reservation/result semantics, which this pure slice does not own.
5. Atomically commit domain changes, event result, case version/audit, and effects
   through CaseService. Workers need transactional load/compare/commit or a
   per-case lock. On races with reply/pause/reschedule/location clear or assignment,
   reload and recompute; never blindly install a transition from an older case
   version. No-op ticks need no new case version. Acknowledge-once and operator
   ownership checks must execute inside that same concurrency boundary.
6. Stable IDs are SHA-256 over canonical case/kind/parent identity. Reminder and
   review IDs derive from occurrence; command reports/attempts/outcomes derive from
   event. Effects have independent stable IDs. Enforce uniqueness at commit/outbox
   consumption, so even a worker recomputed from the same precommit state cannot
   duplicate durable effects. Persist transitions before consuming effects; lost
   responses are retried using C01's durable event outcomes. These effects are
   auditable simulator/UI events, never live SMS/call/dispatch jobs.
7. C01 must validate volunteered need IDs against the authorized case and provide
   only same-case relevant need records to the projection. Grant only reviewed
   operator scopes. Do not pass the domain aggregate/full case to the operator UI;
   use `operator_projection` and audit the read. Map approved snapshot descriptor
   record references to the proposal's stable IDs.
8. `urgent_help_required` instructs the integrator to render its source-backed
   official emergency/local-help resources immediately, including usable contact
   directions. The domain returns honest receiver status/direction, not a resource
   directory or a claim that authorities were notified. Render saved urgent help
   before enrollment/consent interruptions or network/validation failures; offline
   requests remain visibly `queued_local` until C01 accepts them. This renderer is
   required for full C07/application acceptance and belongs to the integrator.
9. Retain domain replay fingerprints until C01 provides equivalent durable replay.
   Bounds are 256 occurrences/reviews, 256 reports/attempts/updates/outcomes per
   record, 32 consented needs and 4,096 domain command receipts. Capacity rejection
   is atomic; nothing silently drops histories or idempotency markers. Production
   archival, retention/deletion, clock trust, pagination and worker scaling remain
   C01 integration decisions. Expiry removes location from operator access but does
   not secretly purge history or unrelated residence data.

## Synthetic verification

Run from the repository root; neither command loads environment files,
credentials, live providers, agent configuration or a running service:

```sh
python3 -m unittest tests.test_check_ins -v
python3 -m backend.stillhere.check_ins.demo
```

The demo enrolls a synthetic household, shares a synthetic place, advances an
injectable clock through reminder/grace, repeats the tick, acknowledges assignment,
records a simulated attempt, shows a pending offline reply, receives it later,
records outcome/unresolved need, explicitly reschedules, pauses and clears
location, then projects the still-visible review. Tests cover that complete flow,
duplicates/restart/stable effects, late and out-of-order replies, no inferred
welfare, consent removal/expiry/offline controls, assignment and spoofed identities,
minimal projection, pure-input preservation, and malformed/unauthorized commands.

Focused verification: **36 tests passed**, and the synthetic CLI demo ran
successfully. Validation is through the local proposal validator; the optional
external `jsonschema` package is not installed in the default Python runtime.
No credentials or live-provider verification were attempted. Shared integration
and frontend/operator acceptance remain separate gates.
