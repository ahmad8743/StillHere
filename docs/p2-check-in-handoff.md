# P2 C11: check-in and location controls

## Current boundary

Open the existing frontend and choose **Menu → Check-ins**. C11 now has a browser-local implementation for enrollment, replies, explicit later times, pause/stop, a help request, and separately consented manual location sharing/removal. The home page shows one compact link after participation or an unsent change; enrollment stays optional.

`frontend/check-in-controls.js` renders the controls and submits versioned commands through the mock adapter. `frontend/check-in-demo.js` provides synthetic transitions for these controls. Neither file implements P1's C07 engine, real message delivery, a staffed receiver, authentication, or operator access. The shared case-service schema and backend are unchanged. All nested record shapes below are proposals for P1 review, not a joint contract freeze.

Check-in and location commands update only `check_in`, `shared_location`, and associated simulated `follow_ups`. They do not append to recovery, finance, or general transcripts, change the finance ledger, or grant location consent from the city-notice preference. Clearing the follow-up location leaves unrelated case facts and the notice-city preference alone.

## Proposed command payloads

All commands retain the existing `0.1` command envelope, `dashboard` channel, stable `event_id`, case ID, expected case version, and original UTC occurrence time. This mock uses UTC timestamps with whole seconds. P1 still supports only its existing intake/fact handlers.

| Type | Payload used by C11 |
| --- | --- |
| `check_in.enroll` | `consent: true`, `due_at`, case `time_zone`, `grace_minutes`, `channel: "in_app_simulation"` |
| `check_in.reply` | `schedule_id`, `occurrence_id`, `reply: "okay_for_now" / "need_help" / "check_later"`; `new_due_at` required only for `check_later` |
| `check_in.pause` | `intent: "pause" / "stop"` |
| `help.request` | Short `message`; optional current `occurrence_id`. Available without enrollment. |
| `location.share` | `consent: true`, `scope: "case_follow_up"`, manually entered `place`, `observed_at` |
| `location.clear` | `intent: "stop_sharing"` |

Enrollment offers one agreed time, rather than assuming a recurring schedule. The case time zone is shown beside the time selection. UI grace choices are 15/30/60/120 minutes; the mock accepts integer periods from 15 minutes to one day. These are demo settings, not validated operational response targets.

Each occurrence carries its schedule/occurrence IDs, due time, grace deadline, reminder-attempt ID, report, and review reference. Reports retain original `reported_at` and demo `received_at`. A reply answers the occurrence; another check-in requires an explicit new time. `check_later` retains the old occurrence in history and creates a new agreed one. Pausing cancels pending scheduled attempts without closing open reviews or revoking separate location consent.

Manual shared locations carry observation/receipt times, a manual source, permission scope, and `simulation: true`. The UI labels locations at least 24 hours old as stale using the controlled demo clock. A recent location is still only last known, never a verified current destination. Removing a location clears the active projection; it is not a complete history/device-data erase.

## Demo clock and review behavior

The check-in clock starts at October 10, 2026, 15:00 UTC (the fixture time). It does not move in the background. Expand **Demo controls** to advance an hour or move past the current grace period.

Advancing records at most one simulated reminder per occurrence. Passing the grace deadline marks the occurrence overdue, with condition unknown, and records one simulated review request. Repeated clock advances reuse that review. A help reply/request can create review immediately. Replies attach their report to an existing review and preserve its ownership/state. No human acknowledgment, real contact attempt, or dispatch is claimed.

Clock transitions and commands use copy-on-write storage. A failed local save leaves the accepted case unchanged. Accepted command retries return `already_applied` before checking the current case version; altered payloads cannot reuse an accepted event ID. C11 event receipts and clock values are demo values, not real server audit times.

## Unsent changes

This slice provides **one unsent C11 change per case**, stored at `stillhere.p2.check-in-pending.v1:<case_id>`. It is a bounded C11 behavior, not the complete C13 offline cache/replay feature.

- Turning on **Simulate offline sending**, or the browser reporting offline, leaves the change visibly unsent. Normal local demo operation requires no network.
- The user explicitly retries; reconnecting or reloading does not send it automatically. The command retains its event ID, payload, original report time, and expected case version.
- A version conflict stays pending. The UI displays current accepted details and requires an explicit **I’ve reviewed it — retry this change** action before using the latest version. A rejected change can be discarded and entered again.
- Unsent pause/stop and location removal never appear accepted. During pending removal, the place is hidden in this page while the UI explains that the demo case still holds it.
- Local storage failures show that the pending change is not saved on the device. The user must keep the page open and retry. A failed discard retains the in-memory pending change.
- The pending record is scoped to the case ID and cannot be submitted into another case. This demo has no real household login/logout boundary.

The mock case is saved under `stillhere.p2.mock-case.v1`. `StillHereMockService.reset()` resets its case and clock. For a fresh check-in walkthrough, also remove the matching pending key from browser storage and reload; chat state is separate. Full opt-in snapshot caching, multiple-event ordered replay, scoped erase/logout, and real late-reply delivery remain C13/P1 work.

## Review and integration still required

JavaScript syntax and diff whitespace checks were performed for this slice. No new tests were added or run. Browser interaction/layout, keyboard/screen-reader behavior, reload/storage failures, and cross-feature regression paths remain unverified. The browser automation tool rejected the local file preview, so no alternate preview route was attempted.

When P1 is ready, agree the payload and nested record schemas, replace fixture transitions with the authenticated C07 transport, use server times, and connect real receiver coverage/status. Verify queued late replies, conflict reconciliation, consent revocation, pause/stop, reminder/review deduplication, and location access through that service. C11 remains `IN_PROGRESS` until those checks and integration are complete.
