# StillHere — Response Partner Discovery

Status: initial desk research and discovery brief; no partnerships or response commitments established.

Scope correction from the user: do not let local partner discovery bog down this planning phase. This document is optional background for a later pilot; selecting a locality, interviewing organizations, and resolving detailed operating procedures are not prerequisites for the high-level MVP plan. No further local discovery is being pursued in this discussion.

Updated: October 10, 2026.

Confirmed by the user: StillHere has no committed response team. The accepted MVP includes optional scheduled check-ins, optional last-shared location, and simulated human follow-up. Selecting a pilot locality and conducting further organizational discovery are deferred. Nationwide resource guidance remains the product goal; a later local pilot would bound human-response operations rather than narrow national referrals.

## 1. Initial finding

An organization doing disaster relief is not automatically available to follow up every missed StillHere check-in. Distinguish a public service referral, an organizational partnership, accepted ownership of a household case, and authorization of a field response.

The recommended discovery priority is a local disaster case-management provider, introduced through a state/local VOAD network or local 211. Red Cross is a relevant welfare/reunification and urgent-service referral candidate. Local emergency management is a coordination stakeholder. The National Guard supports official disaster response; do not design a direct app-to-Guard missed-check-in dispatch path without a specifically established official arrangement.

This prioritization is an inference from the organizations' documented roles, not a confirmed agreement or a guarantee of local capacity.

## 2. Candidate roles and public entry points

| Candidate | Established public role / entry point | What StillHere must verify |
| --- | --- | --- |
| Local 211 / United Way network | Disaster recovery information, local service specialists, and local phone/text/chat/directory routes. 211 also publishes a partnership page. [Disaster help](https://211.org/get-help/disaster-recovery), [partnerships](https://211.org/partner-us). | Whether the local operator accepts third-party referrals; provides ongoing follow-up; supports consented transfers; and can acknowledge/refuse a request. Directory/API access is not a welfare-response commitment. |
| State/local VOAD or COAD | Connects organizations involved in disaster response/recovery. National VOAD identifies state/territory affiliates as a route into local disaster-relief work and describes corporate/community partnerships. [FAQ](https://www.nvoad.org/faqs/), [member directories](https://www.nvoad.org/our-members/). | Which member actually provides case management, welfare inquiry, or field services in the pilot area; who has authority to accept and supervise that work. The network itself must not be assumed to operate a dispatch center. |
| Local disaster case-management provider / long-term recovery group | National VOAD describes skilled, time-limited coordination of survivor recovery, with privacy and survivor autonomy. Catholic Charities describes direct relief and ongoing case management through local agencies. [Case-management consensus](https://www.nvoad.org/wp-content/uploads/DCM-POC-Final.pdf), [Catholic Charities disaster work](https://www.catholiccharitiesusa.org/what-we-do/disaster-relief/). | Active local program, event/geographic eligibility, intake capacity, operating hours, follow-up service, consent, and accepted case ownership. This appears the strongest fit for continuity of recovery care. |
| Local American Red Cross chapter | Shelter/services and disaster reunification routes. Emergency Welfare Inquiries have stated criteria involving disaster-affected people with specified needs; other reunification routes also have criteria. [Official inquiry guidance](https://www.redcross.org/get-help/disaster-relief-and-recovery-services/contact-and-locate-loved-ones.html). | Whether a StillHere-generated concern meets criteria; who may initiate it; what evidence is needed; coverage during the incident; and whether a formal referral relationship is possible. A missed app login is not itself an established inquiry criterion. |
| Local/county emergency management | Coordinates disaster response partners and official local procedures; state guidance emphasizes coordinated, requested volunteer assignments. [Example agency guidance](https://scemd.org/news/volunteers-should-not-self-deploy/). | Pilot area's welfare-check/referral procedure, response authority, service boundaries, field safety, and how the app fits existing coordination. Routine recovery case ownership is not assumed. |
| National Guard | Supports civilian emergency responders during disasters and operates through official state/federal activation and command structures. [Official FAQ](https://www.nationalguard.mil/About-the-Guard/Army-National-Guard/FAQ/). | Any role belongs in coordination with responsible civilian authorities. No direct consumer welfare-referral interface or StillHere dispatch authority has been established. Do not treat the Guard as a routine callback partner. |
| Emergency services | Immediate emergencies use established emergency channels. [911 guidance](https://www.911.gov/calling-911/). | Provide clear user-facing emergency instructions. A StillHere queue is not emergency dispatch and an automatically generated concern is not a confirmed emergency. |

Public entries above are discovery/referral routes, not authorized destinations for automated case transmission. No organization has been contacted during this research. The National Guard FAQ was available through official indexed text but direct fetching returned 403; its precise current operational intake should be confirmed with responsible local authorities. Some FEMA and VOAD-directory pages also could not be retrieved, so no unpublished integration capability is assumed.

## 3. Evidence already available

There are existing product/service patterns to learn from:

- Google Personal Safety lets a user schedule a check-in and select emergency contacts. It demonstrates explicit, time-bounded expectations rather than inference from app use. [Product documentation](https://support.google.com/pixelphone/answer/7055029?hl=en).
- Disaster case-management organizations already structure ongoing contact around a survivor's recovery needs. A trained person or organization owns the relationship; app activity is not its outcome.
- Catholic Charities describes an internal disaster-response app supporting its trained case-manager network. This is evidence that organizations may already have assignment systems, not evidence of an API available to StillHere. Ask how to fit existing workflows before designing a new dispatch system.

Desk research supports these patterns. It does not establish the popularity or effectiveness of either proposed monitoring extreme, nor validate universal 24/48-hour escalation thresholds.

## 4. Recommended balanced model

Use the check-in proposal in `docs/monitoring-design.md` as the starting point:

1. The household opts into an agreed contact time/cadence and safe contact method.
2. It separately authorizes a trusted contact or participating agency to receive specified information.
3. A missed check-in creates an overdue/unknown state, with delivery and connectivity evidence.
4. A staffed receiver reviews the concern, acknowledges ownership, and follows its appropriate contact/referral procedure.
5. Any field response is an organizational decision through coordinated responders. The app records actual acceptance/outcomes, not presumed dispatch.

Use last explicitly shared location with age/source/accuracy. Default to user-described place, city/ZIP, or one-time location permission. Keep current stay and damaged residence separate. Temporary journey sharing can be researched for a later native app; continuous background GPS is not a core requirement. A browser/PWA cannot provide a dependable always-on location service, and a lost connection prevents the server receiving new observations. [Web geolocation specification](https://www.w3.org/TR/geolocation/), [Android background limits](https://developer.android.com/develop/sensors-and-location/location/background).

Do not require location sharing or follow-up consent to access recovery resources. A user-declared "I'm okay for now" is a timestamped report; it does not resolve all recovery needs. An explicit urgent help request follows the immediate-help route without waiting for the scheduled check-in.

## 5. Partner discovery questions

When the team is ready to interview candidate organizations, resolve the following. The questions are preparation, not authorization to message anyone.

| Topic | Questions |
| --- | --- |
| Service fit | Do you handle ongoing recovery follow-up, welfare inquiries, field visits, or only information/referrals? What situations belong elsewhere? |
| Coverage | Which incidents, jurisdictions, households, hours, and languages can you serve? What changes during a major disaster? |
| Intake | Can a survivor or authorized third party initiate a request? What makes it actionable? What information is unnecessary or inappropriate? |
| Ownership | How is a referral accepted, assigned, refused, transferred, and closed? Who supervises unacknowledged or overdue cases? |
| Timing | What check-in cadence, grace/retry policy, and response targets would you approve? How do urgent concerns differ from routine follow-up? |
| Connectivity | How do you interpret failed texts, dead phones, outages, stale location, and late offline replies? Which alternate contact methods are acceptable? |
| Consent/privacy | What survivor consent, safe contact preferences, retention, access restrictions, and identity checks are required? What information can go to a trusted contact versus your staff? |
| Field response | Who can authorize a visit, verify destination relevance, select qualified responders, and coordinate their safety? Can the app receive real outcome updates? |
| Integration | Which existing case/referral tools should we fit? Would an assisted transfer, secure portal, structured export, or API be acceptable? Does your directory access include any case workflow? |
| Capacity | What happens when you cannot accept more cases, are closed, or lose connectivity? What is the honest message and fallback for the survivor? |
| Pilot design | What small cohort and locality could you support? Who reviews false escalation, missed urgent concerns, message burden, and the quality of follow-up? |

A partner should approve the live escalation procedure. An AI-produced risk score or elapsed timer does not substitute for that agreement.

## 6. Required outputs before live welfare follow-up

Create a pilot service map and an agreed operating document naming the response owner, service/eligibility boundaries, staffed hours, accepted intake channel, minimum data/consent, acknowledgment procedure, timing policy, emergency route, unavailable-capacity fallback, and outcome/closure process.

Track four separate states: referral prepared, referral transmitted, accepted/assigned, and outcome confirmed. Only real acknowledgment can establish accepted ownership. A provider may decline a referral; it must not silently remain "help on the way."

Maintain an auditable unassigned queue and a supervisory review process for accepted cases whose owner becomes unavailable. Track next action and due time rather than rely on logins to show care continuity. A public national referral directory does not provide national staffed monitoring coverage.

## 7. 12-hour prototype boundary

With no committed team, build a clearly labeled demonstration of check-in enrollment, overdue transitions, consent/location metadata, and an operator accepting and recording a follow-up. Use synthetic households and simulated messages. Do not make live volunteer calls, field visits, or continuous tracking part of the MVP promise.

Nationwide guidance remains possible while a later human-follow-up pilot starts in one locality. Partner discovery and agreement are external work with uncertain timing, not activities guaranteed to finish inside the 12-hour coding timebox.
