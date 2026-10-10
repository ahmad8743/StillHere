# StillHere — Check-ins and Welfare Follow-up

Status: supporting design research. The user-approved MVP scope is integrated into the authoritative [project specification](project-specification.md): optional scheduled check-ins, optional last-shared location, and simulated human follow-up. Live monitoring, calls, rescue, and volunteer dispatch are outside the MVP.

Planning scope: the user wants to keep this discussion high-level. The prototype demonstrates the accepted workflow with simulated outreach; detailed local partnerships and live response operations belong to a later pilot. The detailed material below is background, not additional requirements or a discovery checklist needed before the MVP plan can proceed.

Updated: October 10, 2026. No contacts have been notified, no tracking has been activated, and no volunteers have been dispatched.

## 1. Recommended direction

Offer optional, agreed check-ins with human follow-up based on the household's circumstances. Use user-provided or one-time shared location by default. Consider optional, time-limited journey sharing in a later native implementation. Continuous location collection is not required to receive resources or recovery guidance.

Maintain accountability for each open follow-up: the last explicit check-in, unresolved need, next expected contact, authorized recipients, and who has accepted responsibility for responding. App activity is a separate operational signal; it does not prove that a survivor is safe or has received help.

Distinguish two services:

- **Recovery follow-up:** review open tasks, unmet needs, deadlines, and financial gaps with the household.
- **Welfare follow-up:** respond to a missed agreed check-in or an explicit concern, with human assessment and an appropriate responder/referral.

The specification now includes the narrow check-in feature and simulated follow-up queue. General proactive outreach and a full caseworker console remain future scope.

## 2. Evidence and limits

| Evidence | What it supports |
| --- | --- |
| Google Personal Safety provides scheduled Safety Checks with selected contacts and an emergency-sharing response if a check is missed | Scheduled, user-controlled check-ins are an established product pattern. This is a native-device example, not a service that StillHere inherits. [Documentation](https://support.google.com/pixelphone/answer/7055029?hl=en). |
| Red Cross describes Emergency Welfare Inquiries and other reunification requests under specific disaster-related criteria | Human welfare/reunification inquiry is an existing disaster-service practice. It is not a universal missed-login service or a committed StillHere partner. [Reunification guidance](https://www.redcross.org/get-help/disaster-relief-and-recovery-services/contact-and-locate-loved-ones.html). |
| National VOAD disaster case management consensus emphasizes skilled human coordination, survivor autonomy, privacy, and coordination across organizations | Recovery follow-up should complement accountable human services and preserve survivor control. [2019 consensus](https://www.nvoad.org/wp-content/uploads/DCM-POC-Final.pdf). |
| National VOAD volunteer-management consensus emphasizes organizational structure, appropriate assignments, safety, supervision, and training | A field response needs a responsible organization and qualified people. [2024 consensus](https://www.nvoad.org/wp-content/uploads/NVOAD-Volunteer-Management-POC_Final-Ratified-May-2024.pdf). |
| South Carolina emergency management advises against unrequested/self-deployed volunteer response | Do not turn an automated timer into instructions for uncoordinated volunteers to enter a disaster area. [Agency guidance](https://scemd.org/news/volunteers-should-not-self-deploy/). |
| W3C geolocation specifies permission, timestamps/accuracy, and updates for fully active visible documents | A browser/PWA cannot be relied on for always-on background GPS. Position is a device observation with uncertainty. [Specification](https://www.w3.org/TR/geolocation/). |
| Apple and Android document permission, background execution, and battery-related limits | Native background tracking is technically possible in some circumstances, but cannot guarantee continuous server visibility or a person's exact location. [Apple](https://developer.apple.com/documentation/corelocation/handling-location-updates-in-the-background), [Android](https://developer.android.com/develop/sensors-and-location/location/background). |

These sources establish relevant practices and technical limits. They do not establish a universal 24/48-hour disaster follow-up standard, quantify popularity, validate StillHere's operational effectiveness, or supply a staffed response partnership.

## 3. Assessment of the two proposed extremes

| Approach | Useful part | Main failure mode |
| --- | --- | --- |
| Missed-login timer with notification, call, then field visit | Low implementation burden; can identify people who may need follow-up | Inactivity is ambiguous. Recovery, battery/network failure, shared phones, and app abandonment can all look the same. A fixed 48-hour wait may also be inappropriate for a stated urgent need. |
| Continuous location tracking | May provide more recent device coordinates when supported and authorized | Missing updates still do not identify the reason or the exact point of lost connection. A phone can be elsewhere, powered off, unable to upload, or have permission revoked. Continuous collection increases sensitivity and requires a different mobile architecture. |
| Agreed check-ins with human review | Clear expectations, low-bandwidth interaction, and proportionate data use | Requires contact/delivery failure handling and a real, staffed follow-up process before live welfare promises are made. |

An absence of data means the current status is unknown. It must not automatically become "safe," "in danger," "missing," or "volunteer dispatched."

## 4. Proposed household experience

After immediate needs are addressed, ask whether the household wants follow-up. Declining or later pausing it must not block recovery resources or fintech features.

The household chooses:

- Contact channel, safe contact times, and whether messages can identify StillHere.
- A check-in time or recurring cadence, a grace period, and an expected limited-connectivity period.
- A trusted contact and/or participating organization if available, with separate permission to share information with each.
- The information recipients may receive, including whether to share a last known location.
- Pause/stop controls and a way to change the plan when circumstances change.

A check-in offers plain replies such as "I'm okay for now," "I need help," "Contact me later," and "Pause check-ins." An "okay" reply records a report at that time; it does not resolve other unmet needs or guarantee ongoing safety.

Illustrative scheduling choices are a daily recovery check-in for someone requesting close follow-up, a less frequent agreed appointment for someone stably housed, or a specific arrival check after travel to a shelter. These are design examples, not expert-validated safety intervals. A response partner must approve any live welfare cadence and operating procedure. Do not enforce 24/48 hours universally.

An explicit urgent help request immediately exposes appropriate emergency contact instructions and creates an urgent review request when a staffed receiver exists; it does not wait for the normal timer. Do not imply that an unstaffed app has alerted emergency services.

## 5. Escalation and accountability

Use explicit workflow states, separate from the household's reported condition:

```text
Scheduled -> Due -> Reminder attempted -> Overdue / contact uncertain
                                      -> Human review requested
                                      -> Assigned and acknowledged
                                      -> Contact attempted / referral considered
                                      -> Outcome recorded / next check-in agreed
```

Also support paused, canceled, and unassigned states. Message queued/sent/delivered/failed is separate from the survivor's reply; delivery alone is not a welfare check. Repeated timer runs must not create duplicate cases or notifications.

1. At the agreed time, attempt the authorized reminder.
2. On nonresponse, record an overdue check-in and inspect delivery status, expected connectivity, and relevant reported concerns. Apply only the consented retry/grace policy.
3. If follow-up is warranted, route to the authorized trusted contact or staffed organization. Log the request as unassigned until a real receiver accepts it.
4. The receiver reviews the known circumstances, tries approved contact methods, and considers relevant welfare/reunification or emergency-service referrals. The AI can prepare a concise summary; it does not authorize a field visit.
5. A field assessment, when appropriate, is an organizational decision with verified assignment, coordination, and responder safety procedures. Avoid public volunteer maps of survivor locations.
6. Record the outcome, unresolved needs, next contact, and owner. If the owner cannot respond, return the case to a supervised queue rather than leaving it silently assigned.

The follow-up queue shows consent scope, last explicit check-in, next due time, known unmet needs, last location with age/accuracy, delivery attempts, assignment acknowledgment, operating coverage, and outcome. A receipt acknowledgment and response target must be defined with a real partner; queued does not mean someone is on the way.

A widespread connectivity outage can make many households overdue together. Annotate the shared failure, avoid flooding duplicate outreach, and retain unknown household status. Do not assume everyone is either safe or endangered because of an outage.

Prioritization uses explicit requests, known urgent unmet needs, agreed check-in plans, and relevant official hazard context. A stale coordinate inside a warning area is a review signal, not proof of present exposure. Avoid opaque model-generated danger scores or automatic escalation based on demographic labels.

## 6. Location and contact information

Default to city/ZIP, a user-described current place, or an optional one-time location fix. Store time, source, accuracy when available, intended use, recipient permissions, and expiry/retention policy. Label the latest observation "last shared location," never current if it is stale.

Keep current stay, damaged residence, mailing address, and last device location distinct. A destroyed home is not automatically a useful field-search destination. Permanent addresses and movement history should not be required just to provide follow-up.

For a later time-limited sharing feature, display who can see it, its purpose, and when it stops. Allow revocation and prohibit use for unrelated purposes. A functioning native background implementation can improve observations, but GPS reception without connectivity cannot transmit new coordinates to StillHere's server. Tracking a phone is not verification of the owner's welfare.

Precise addresses/coordinates are available only to authorized people handling that case. Safe contact preferences and recipient selection matter for shared phones and survivors whose location must not be disclosed to particular people. Declining or revoking location sharing must not be treated as evidence of danger.

When an offline check-in synchronizes later, retain its original report time and server receipt time. Reconcile it with any open human follow-up; notify the assigned reviewer of the new information rather than silently cancel a response already underway.

## 7. Prototype recommendation

For the 12-hour build, demonstrate optional check-in enrollment, a selected next-contact time, explicit reply buttons, last-contact/location metadata, a deterministic overdue-state transition, and a small simulated operator queue with assignment and outcome recording.

Use a controllable demonstration clock and labeled message/contact events. No real volunteer dispatch, unsolicited contact, continuous background tracking, or staffed-monitoring promise is included. Welfare reminders and follow-up remain simulated in this MVP. Live human-response integration requires a separately scoped pilot with a committed organization, service area, hours, acceptance procedure, and capacity plan.

The accepted specification assigns case/check-in state and timer policy to work package A and check-in/queue UI to D. B supplies hazard/resource context but cannot infer welfare; C may supply a known essential-expense gap as recovery context, without treating it as proof of an emergency. Prioritize core follow-up behavior over optional Plaid polish if the 12-hour capacity requires a tradeoff.

## 8. Acceptance and pilot measures

- No missed login by itself marks someone missing or triggers a field visit.
- An explicit help request bypasses routine follow-up timing and shows honest receiver/coverage status.
- A message delivery receipt, background location ping, or incidental login cannot establish that the household is safe.
- Failed deliveries, shared outages, duplicate timer runs, revocation, pauses, and late offline replies have distinct outcomes.
- Stale/damaged-home locations are not represented as verified destinations.
- Assignment remains unaccepted until acknowledged; every accepted follow-up has an owner, next action, and recorded outcome.
- Consent limits which recipients receive which information; all case access is audited and private.

For a later partner pilot, measure time to acknowledged follow-up, unresolved overdue cases, successful reconnection, false escalation, message burden, owner capacity, and survivor understanding/control. Validate thresholds and workload with disaster-response practitioners before scaling.

Confirmed: the user has no committed response team and has deferred detailed partner discovery. The initial [partner-discovery brief](response-partner-discovery.md) is background for a later pilot. Until a staffed partnership is established, demonstrate the workflow and explicitly distinguish it from an operational welfare-monitoring service.
