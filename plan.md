# Lovable Build Plan — StillHere P2 Experience

## Purpose

Build a polished, mobile-first frontend prototype for **StillHere**, a disaster recovery companion. It helps a household find next steps, understand near-term finances, and optionally manage check-ins. This is a frontend design/build handoff for Lovable. Use realistic interactions and synthetic data; do not connect real services.

The interface should feel calm, trustworthy, practical, and easy to use under stress. Keep language direct and plain. Make the first useful help easy to reach without requiring a complete profile.

## Current direction update — use this over the earlier screen list

The household-facing experience should be **crisis-first and uncluttered**. Keep finance available from a small header menu, and keep check-ins, a long task dashboard, and an operator queue out of primary household navigation.

- The signed-in user's saved profile city is visible in the header and can be corrected. Treat it as a user-provided city, not GPS or proof of current presence.
- On first launch, ask whether the user wants to share their current city for local notices. Offer the saved city, changing the city, or “Not now.” Do not request precise GPS coordinates in this prototype. If they decline, continue to general help without showing a location-matched notice; allow them to opt in later.
- When a matching local incident notice exists, show one compact in-app prompt: name the incident and area, then ask whether the person is affected, unsure, or needs other help. In this prototype, the Louisiana hurricane is labeled synthetic demo data.
- “Yes, I’m affected” leads straight into a guided chat. Let the person select multiple needs before continuing, then ask which practical obstacles may make it harder to get help (for example transport, cost, caregiving, accessibility, phone access, language, or missing ID/Social Security documents). Both questions allow multiple selections, “skip” where appropriate, and free typing. Do not ask for or store an SSN; record only the missing-document barrier. Check immediate safety before presenting a short list of next steps in the chat.
- The home screen offers “Continue chat” for an unresolved conversation and a simple way to start a new one. Do not make users repeat information they already gave.
- The header menu includes a free-form “General chat” entry for questions outside the guided recovery flow. Keep its transcript separate from both recovery and finance conversations.
- Keep “In immediate danger? Call 911” visible on the home and chat screens, including while the app is open without an app data connection. Do not claim that the app itself contacts emergency services.
- Keep the crisis flow uncluttered. Put Home, Recovery chat, and Finances in a small header menu; keep city editing available from the header. Do not add profile, follow-up, or mock-operator controls to household navigation.
- The Finances page is a focused, clearly labeled synthetic example: available funds, daily essentials, one-time cost, first projected gap, and a reminder that unreceived aid is not cash on hand. Do not imply these example numbers belong to the user; future financial values must use the shared finance contract and explicit user input.
- The home screen also offers a direct “Chat about finances” path. Finance and recovery are separate saved conversations: each has its own transcript, progress, and topic context. Switching between them must not append finance messages to recovery, or let finance details alter recovery answers. The saved city may be shown in both threads as shared profile context. Finance starts with choices for available money, upcoming costs, or pending aid, plus free typing. The local prototype uses transparent canned replies until the real assistant/finance integration is connected.

This update supersedes the earlier multi-screen household dashboard scope below wherever they conflict. The earlier feature notes remain background for later iterations.

## Product context

StillHere is one coherent recovery workspace. Conversation and direct controls represent the same household state. The household can skip questions, leave answers unknown, correct details later, and resume its case. The current app backend is an early local prototype; this Lovable build should use a replaceable mock-data layer until integration is planned.

This is a demonstration, not an operating aid or emergency-response service. Resource and contact examples must be clearly identified as synthetic/demo content. Check-in reminders and operator follow-up are simulated. Do not imply that a human has been contacted, that an organization accepted responsibility, or that help is on its way.

## Build scope

Create a responsive web app with these connected views:

1. **Welcome and quick intake**
   - Briefly explain the product and offer a prominent “Get help now” path.
   - Ask only a few optional questions: what help is needed now, what happened, priority needs, who needs support, and current city/ZIP if useful.
   - Allow “Skip” and “Not sure” for each question. Never block urgent guidance on intake completion.
   - Do not ask for full name, government ID, bank credentials, or document uploads.

2. **Household recovery home**
   - Use a responsive navigation pattern: compact bottom navigation or menu on mobile; clear sidebar/navigation on desktop.
   - Show a concise greeting, current case status, immediate needs, and a small prioritized “Next steps” list.
   - Include a chat/conversation panel with focused questions, suggested replies, and a clear state for sending a message. Use deterministic mock replies or canned flows; do not call an AI/model API.
   - Provide direct controls that update the same client-side mock case as the chat. Include editing a fact, marking a step complete or blocked, and entering a financial update.
   - Make unknown, user-reported, source-supported, conflicting, and stale information visually distinct and understandable.

3. **Money and 14-day outlook**
   - Show accessible money separately from inaccessible funds, restricted aid, confirmed noncash support, and future/unreceived aid.
   - Show a dated 14-day forecast, first projected gap, daily/one-time expenses, assumptions, and a small scenario comparison.
   - Include editable mock entries for balance, expense, aid status/timing, and confirmed support. Clearly distinguish actual amounts from hypothetical scenario assumptions.
   - Use the four synthetic scenarios in `docs/project-specification.md` / `docs/finance-design.md` as the canonical demo values:
     - $300 opening cash; $20/day food + $40/day lodging + $5/day transport; $30 recovery cost on day 1.
     - No support/aid: first gap day 5, $55.
     - Food and lodging coverage days 1–7: first gap day 11, $25.
     - Same coverage plus hypothetical $500 receipt day 8: no gap in 14 days; ending projected position $280.
     - Same coverage plus hypothetical $500 receipt day 12: day-11 gap remains $25, ending projected position $280.
   - Label all values and support arrangements as synthetic demo data. A forecast concerns entered expenses only; do not describe it as a prediction of survival or total household runway.

4. **Check-ins and optional location**
   - Provide an opt-in check-in control with a mock next time, contact preference, and pause/cancel controls.
   - Offer clear simulated replies such as “I’m okay for now,” “I need help,” and “Check later.”
   - Let the user optionally enter or clear a last-shared place. Show when it was shared and who can see it. Do not request continuous location tracking.
   - Show overdue as “check-in overdue / status unknown,” not as a confirmed emergency. A missed login alone must not trigger escalation. All reminders/actions are labeled simulated.

5. **Demo follow-up queue**
   - Add a separate, clearly marked demo/operator view, not mixed into household navigation by default.
   - Show only consented synthetic case context: last explicit report/time, due/grace time, relevant needs, optional last-shared location with age, simulated attempts, assignment state, and next action.
   - Let a demo operator acknowledge a synthetic request, record a simulated contact attempt, and record an outcome/next action.
   - Keep requested, acknowledged/assigned, attempted, and outcome-recorded states separate. An unassigned item must never say or imply that someone is responding.

6. **Offline and printable states**
   - Include a visible offline/sync status and a sample queued change with its original time. Show when a change is pending or a conflict needs review; never imply it was saved remotely until acknowledged.
   - Include a print-friendly recovery summary with user-selected next steps, dates, and contacts. Sensitive finance/location details are excluded unless deliberately selected.

## Visual direction

- Design for a phone first, then scale cleanly to tablet and desktop.
- Use a quiet, high-contrast palette with warm neutral backgrounds and a restrained deep-blue/teal accent. Use red only for urgent states and pair color with text/icon labels.
- Favor readable type, generous spacing, short sections, clear hierarchy, and large touch targets. Avoid dense admin dashboards, tiny charts, decorative gradients, and alarmist disaster imagery.
- Use simple cards for needs, next steps, forecast, aid, and check-ins. Charts should have readable labels and a text/table equivalent.
- Provide visible focus states, keyboard operation, semantic headings/labels, and accessible contrast. Do not communicate state by color alone.
- Make the household screens reassuring without hiding uncertainty. Show source, freshness, limitations, and demo labels where relevant.

## Mock data and architecture requirements

- Keep all synthetic content in a dedicated fixture/mock module, separate from view components.
- Create a small adapter/service boundary for reads and commands so the mock implementation can later be replaced with the StillHere API.
- Shape the main mock case like the current `CaseSnapshot` in `contracts/case-service.schema.json`: `contract_version`, `case_id`, `case_version`, `updated_at`, `time_zone`, `household_mode`, `facts`, `needs`, `evidence`, `resources`, `plan`, `applications`, `finance`, `check_in`, `shared_location`, `follow_ups`, `conversation`, `components`, `sources`, and `notices`.
- Include a `contract_version: "0.1"` on mock requests/results where appropriate. Preserve stable IDs and timestamps in demo events.
- Use a representative synthetic household: one caregiver, two children, lost home/documents, mobility initially unknown, and $300 accessible cash. Add a “no car” correction flow that updates the affected next steps and relevant costs while preserving completed steps.
- Mark seeded resources, contact details, source notices, and operator records as demonstration data. Do not invent live resource capacity, eligibility, confirmed aid, or partner availability.
- Keep the financial calculator/UI client-side and deterministic for the supplied demo cases. Do not let the model calculate money or mutate state.
- No real bank linking, Plaid, live SMS/email, geolocation tracking, provider API calls, authentication claims, external submissions, or real-world follow-up.

## Interaction rules

- Chat and direct controls update one shared mock state; navigating between views must preserve the edits for the current browser session.
- A fact correction retains the previous value in a visible history/detail affordance and records when it was reported.
- A repeated command/event must not create duplicate financial effects. For the mock, demonstrate a retry as “already applied” or keep the update idempotent.
- Unknown amounts remain “unknown”; do not replace them with zero. Unreceived aid is not counted as accessible money.
- If inputs conflict or a mock action cannot be applied, show a useful plain-language message and retain the previous state.
- Provide a reset-demo control so the walkthrough can return to its initial synthetic state.

## Suggested walkthrough

1. Start intake, skip mobility, and reach the recovery home without completing every question.
2. View a source-labeled urgent/essential resource and the first next steps.
3. Open the finance view and compare the four forecast situations, including the day-11 gap when aid arrives on day 12.
4. Correct mobility to “no car”; show relevant steps/costs change while completed unrelated work remains intact.
5. Add a mock expense or update aid and show the dashboard and forecast reflect the same state.
6. Opt into a simulated check-in, mark it overdue using a demo clock/control, and show status as unknown.
7. Open the operator demo queue, acknowledge a request, record a simulated attempt/outcome, and make ownership/status explicit.
8. Toggle offline mode, queue a mock update, then show replay/conflict status. Open the print view and select which details to include.

## Delivery expectations

- Implement the connected prototype with clean reusable components and responsive layouts.
- Include realistic empty, loading, error, unknown, stale, offline, pending, and completed states.
- Keep the mock API boundary and fixture content easy to inspect and replace later.
- Include a short README explaining how to run the prototype, where fixtures live, how to reset the demo, and which interactions are simulated.
- Do not claim real backend integration. Keep setup simple and report any incomplete views or interactions clearly.

## Existing project references

- Product scope and user journey: `docs/project-specification.md`
- Finance calculations and behavior: `docs/finance-design.md`
- Shared case/command boundary and P2 ownership: `docs/contracts-and-progress.md`
- Current executable case-service JSON Schema: `contracts/case-service.schema.json`
- Check-in and location guardrails: `docs/monitoring-design.md`
