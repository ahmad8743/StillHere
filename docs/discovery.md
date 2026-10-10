# StillHere — Product and Architecture Discovery

Status: historical discovery record. Superseded by the consolidated [project specification](project-specification.md).

Updated: October 10, 2026.

The project folder is a new repository with no existing implementation. The decisions below are recommendations unless explicitly labeled as user requirements. The final project specification should replace pending product decisions with agreed choices, define high-level architectural responsibilities and acceptance criteria, and identify separately scoped future work. Provider access and policy changes cannot be eliminated as uncertainties; the eventual implementation must define verification tasks and fallback behavior.

Scope clarification from the user: this session is for ideation and a high-level project specification. Separate sessions will resolve implementation. Model variants, endpoints, hosting, SDK configuration, and infrastructure details are deferred and do not block this specification.

## 1. User-stated purpose

Help survivors of U.S. national crises who have lost access to resources, documents, or support:

1. Reach urgent survival resources.
2. Follow a feasible sequence of steps to recover documents and obtain assistance.
3. Monitor finances and budget through recovery.

The AI agent must ask useful follow-up questions, act with incomplete information, understand current disasters, produce interactive dashboard elements, reason about prerequisites, and adapt when circumstances change. The final specification must be suitable for implementation by other coding agents. This discovery phase does not begin implementation or delegate agent work.

Confirmed requirements: deliver an MVP within 12 hours of dedicated prototyping with coding agents; provide nationwide recovery guidance across multiple crisis types; try to support both displaced users with intermittent smartphone internet and users with little or no internet. The user subsequently accepted the recommended product defaults and financial direction. The consolidated specification now defines the implementation handoff and routine defaults.

Confirmed agent stack: Strands Agents SDK with a Qwen model hosted on Akamai Cloud. The user reports receiving Strands-related credits, but no specific AWS hosting requirement or credit entitlement has been established. Exact model and deployment details belong to later implementation sessions.

## 1A. Proposed boundary for the 12-hour MVP

The user accepted the recommended overall proposal before requesting a more concrete fintech design. Accepted defaults are a demonstrable prototype rather than public operating readiness; floods, storms/hurricanes, wildfires, and earthquakes; urgent essentials, document recovery, aid, and finances; source-backed resource discovery and user-reviewed application answers/call scripts; manual finances and dated scenarios connected to recovery costs; saved/printable plans and a text access path; reviewed shared program rules with private household records; and reassessment on user changes and return. Uploads, bank imports, live SMS, and proactive reminders are optional extensions, not conditions for completing the core prototype.

The following architectural recommendations operationalize that scope. Concrete infrastructure and integration choices remain deferred to implementation sessions:

- One complete household journey: urgent resource discovery, a feasible recovery plan, a new constraint that triggers replanning, task persistence, and a financial outlook.
- One coordinating conversational agent with typed tool calls into application services. Separate coding-agent work packages are an implementation strategy; multiple autonomous runtime agents are not required.
- A mobile-friendly web application with persistent case data, a small set of fixed dashboard components, and clear live-data, seeded-data, unknown, and stale states. Add deliberate cached-plan behavior and define a text-channel path for users without mobile data.
- Nationwide routing to relevant official resources, supported by a bounded, manually reviewed program catalog with explicit jurisdiction and source-backed requirement expressions. Retrieve and verify jurisdiction-specific rules when needed. Keep the shared knowledge model extensible, but defer an automated nationwide ingestion/review system unless the core journey finishes early.
- Live public disaster-data adapters where reachable. Record external failures explicitly; any stored demonstration incident must be labeled and cannot be represented as current.
- A real deterministic cash-flow and scenario engine using user-entered cash, expenses, and aid status. Make read-only bank imports an optional extension unless the user considers them essential.
- Resource referrals and official application links. Submission, third-party messaging, and bookings remain a separate authority decision.
- Verify the example family journey, no-car replanning, unknown prerequisites, unreceived aid exclusion, data-source failure, and persistence across reloads before expanding scope.

Proposed completion evidence: a runnable MVP, documented setup, source-linked catalog, labeled fallbacks, and an end-to-end demonstration that exercises real case updates and financial calculations. A 12-hour prototype cannot establish comprehensive national coverage, real-time shelter capacity, or production operating readiness; those outcomes need separately scoped work.

## 1B. Low-connectivity and no-internet access — discussion proposal

Supporting both user groups is confirmed; the channel scope is still being worked out. Distinguish these conditions rather than treating them as equivalent:

| Condition | Proposed behavior | Limits and decisions |
| --- | --- | --- |
| Intermittent mobile internet | Cache the application and a user-selected recovery plan; allow task updates and manual financial entries offline; synchronize on reconnect | The application and plan must have been obtained while connected. Show pending synchronization and source timestamps. Sensitive local storage requires an explicit choice and a clear erase action. |
| No mobile data/Wi-Fi, but SMS works | Text conversation and concise equivalents of next step, resource details, task status, and financial summaries, backed by the same case service | The server still needs internet and the user still needs working cellular SMS. Real sending requires a provider, credentials, a sender usable for this purpose, and verified delivery. A simulator demonstrates behavior but is not a deployed access channel. |
| No internet or cellular service | Previously saved plan, essential contact/address details, local task/finance updates, and an exported/printed recovery summary | No live alerts, newly discovered shelters, or server-agent responses can arrive until connectivity returns. A first-time user with no installed/cached material needs a physical or assisted distribution route. |

Recommended application design: one case/planning service with web and text renderers. Offline manual inputs receive stable IDs and synchronization status. On reconnect, reconcile changes before replanning; preserve completed work, detect conflicts, and do not label a queued message as answered or a queued action as submitted. Detailed synchronization semantics remain to be specified.

For SMS, resource answers should include essential address/contact information in the message itself, since a web link alone cannot help someone without internet. Avoid asking for full identity numbers, bank credentials, or raw documents over SMS. Case linking, shared-phone access, consent, and notification behavior need explicit choices.

External timing dependency: Twilio's current U.S. 10DLC onboarding documentation states that campaign review takes 10–15 days. Its current trial documentation also limits recipients and message content. Therefore, a new Twilio account cannot be assumed to deliver an unrestricted live SMS MVP within 12 hours. Confirm an existing usable sender or select a clearly labeled simulator as a prototype deliverable. Other providers require their own validation. [10DLC onboarding](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart), [trial limitations](https://www.twilio.com/docs/usage/trials/try-out-sms).

Service-worker caching can support the proposed offline application behavior after installation and caching; it does not supply new remote data without a connection. [MDN service-worker guide](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers), [offline operation](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation).

## 2. Proposed product model

Confirmed product direction: the agent is the central backend workflow. It creates and maintains the user's persistent recovery file through tool calls, and that file supplies the user's dashboard. The user wants a short phase of general multiple-choice questions before chat and agrees that conversation and direct dashboard controls should both be available. The concrete meaning of a file in storage is deferred to implementation; at the product level it is a living recovery record, not just a chat transcript.

StillHere maintains that recovery record with three connected views: immediate needs, recovery actions, and financial outlook. Conversation and dashboard interactions update the same durable state. The agent decides what to learn, retrieve, plan, and display; tools carry out validated record updates and financial calculations.

### Proposed contents of the recovery file

- Household circumstances: current and affected locations, dependents, access needs, mobility, communication access, and user priorities where relevant.
- Immediate needs: what is urgent, what is already covered, and what remains uncertain.
- Evidence and documents: what the household has, what is missing, acceptable alternatives, and which facts are user-reported or source-confirmed.
- Recovery plan: ready actions, blocked actions, completed work, deadlines, requirements, estimated costs, and alternative paths.
- Applications: stage, outstanding evidence, correspondence the user reports, and expected next action without inventing provider status.
- Finances: accessible money, essential expenses, recovery costs, aid lifecycle, restrictions, and explicit forecast assumptions.
- Open questions and history: unresolved facts, changes in circumstances, reasons for plan revisions, and source verification times.

Store sensitive facts only when needed and volunteered; these categories are not a requirement to collect every field before providing help. Keep shared program knowledge separate from each household's private file.

The main promise is a feasible next step with a reason, verified contact or destination, known requirements, estimated effort or cost, and a fallback when the step cannot be completed. Finding an option does not mean the provider accepted the household or reserved a place.

### Immediate needs

- Ask about current safety and the most urgent need before collecting a detailed profile.
- Discover shelter, food, water, necessary health services, charging, transport, and other relevant local support.
- Show source, last verification time, geographic coverage, accessibility information, and whether availability is confirmed or unknown.
- Preserve official emergency instructions; provide a direct route to emergency services or local responders when indicated.
- Do not delay resources that do not require identity documents while constructing document recovery steps.

### Recovery actions

- Track document replacement, aid applications, housing, and other agreed recovery categories.
- Model alternative proofs, phone or in-person options, deadlines, fees, fee waivers, mailing address requirements, and transport constraints where supported by sources.
- Separate initial application requirements from evidence that can be supplied later.
- Distinguish potential eligibility, unknown eligibility, application submission, and provider approval.
- Expose a manageable set of immediate actions while retaining the longer plan.

### Financial outlook

- Work for users with cash only, missing bank access, irregular income, and uncertain assistance.
- Connect recovery costs and opportunities to a dated household cash-flow forecast.
- Keep available money, restricted assistance, noncash resources, debts, and uncertain future receipts distinct.
- Use explicit assumptions and deterministic calculations that can be reproduced and corrected.

## 3. Adaptive agent behavior

Recommended loop:

1. Read the latest case state and identify urgent needs.
2. Ask a small number of questions that materially change the next action.
3. Retrieve relevant sources and structured program rules.
4. Generate candidate steps and alternatives.
5. Validate requirements, deadlines, known constraints, source freshness, and financial calculations.
6. Save a versioned plan and render interactive components.
7. Replan when the user changes facts, a task becomes blocked, a program changes, or a deadline approaches.

The agent may take internal actions such as finding resources and updating a proposed plan while information is incomplete. Unknown facts stay unknown; a skipped question is not a negative answer. Suggestions based on an assumption identify it. Important inferred facts require user confirmation before they support external applications or financial decisions.

Case fields should distinguish current location, damaged residence, and relevant document-issuing jurisdiction. They should also represent household composition, mobility, phone and internet access, languages, existing documents, immediate needs, and money where voluntarily provided. Store provenance and a timestamp for each fact; do not collect a full sensitive profile at intake.

Example adaptation: “I do not have a car” changes the transport constraint, blocks car-dependent steps, and prompts comparison of verified transit, remote service, mobile assistance, or supported transport options. Completed tasks remain completed; unrelated tasks do not reset.

### First-use experience: selection, conversation, dashboard

Confirmed flow direction: initial general multiple-choice selections precede conversation, and both conversation and direct dashboard controls can maintain the recovery file.

Recommended details:

1. Offer a short set of plain-language selections with an urgent-help entry route and a way to skip or indicate uncertainty.
2. Send the answers to the agent as user-reported context. As soon as there is enough useful context, it creates a partial recovery file and displays initial help. A complete profile is not required.
3. Begin the conversation with a brief acknowledgment of the selected needs and one useful follow-up. Do not repeat answered questions or assume unselected needs are absent.
4. Resource and next-step cards appear as verified information becomes available. Unknown amounts, requirements, and availability stay visible as unknown.
5. The agent asks further questions when answers would change the next action, filling the file progressively.
6. The user can respond through conversation or dashboard controls. Either route changes the same record and prompts relevant replanning.
7. A returning user resumes from the existing file; the agent checks whether circumstances changed rather than repeating intake.

Proposed selection groups; exact wording and order are still open:

| Question | Suggested choices | Behavior |
| --- | --- | --- |
| What kind of help do you need right now? | Urgent safety help; essentials for today; recovery steps; unsure | Single choice for initial priority; urgent help stays accessible throughout intake |
| What happened? | Flood; storm/hurricane; wildfire; earthquake; another crisis; unsure | Self-reported event type; later match relevant official incident context without requiring the user to know an incident name |
| What would help most? | Shelter; food/water; health-related support; transport; lost documents; aid applications; managing money; unsure | Multiple selection; selecting an item does not establish eligibility or service availability |
| Who needs support? | Just me; children with me; other adults with me; I am helping someone else | Permit combinations or clarify the household later; names and detailed personal data are not needed here |

Location should be optional city/ZIP input or permission-based location selection, not a long nationwide multiple-choice list. Ask it when it is needed to find local resources. Current location and damaged residence may differ. Transport, exact document availability, accessible cash, and other details are contextual follow-ups rather than compulsory initial questions for everyone.

For text-only access, use short numbered equivalents of the same selection groups and allow the user to describe the situation directly. For a user who skips selections or answers “unsure,” retain unknowns and ask only what is needed for the next useful action.

The initial selections shape the first questions and dashboard priorities; they must not lock the user into a fixed recovery journey. Later corrections can change both the plan and the dashboard.

Initial conversation on opening the application does not imply unsolicited outreach or a background notification service. Whether the agent later checks in about deadlines, changed resources, or forecast shortfalls remains a separate product choice.

## 4. Current-disaster and resource data

No single source established by this research covers live hazards, declared assistance, service directories, and actual shelter availability. Build separate adapters with a normalized internal representation and source-specific freshness policies.

| Source | Proposed role | Evidence and integration status |
| --- | --- | --- |
| National Weather Service API | Geographic weather alerts and official instructions | Public documentation verified. Examples include `/alerts/active?point=latitude,longitude`. Documentation requires an identifying User-Agent. API integration has not been tested. [API documentation](https://www.weather.gov/documentation/services-web-api), [alert geolocation guidance](https://www.weather.gov/media/documentation/docs/NWS_Geolocation.pdf). |
| USGS earthquake feeds/catalog | Candidate earthquake incident context if earthquakes are included | Official feeds and API documentation identified; integration has not been tested. An earthquake event record does not establish local service availability or household eligibility. [Feeds](https://earthquake.usgs.gov/earthquakes/feed/v1.0/), [catalog API](https://earthquake.usgs.gov/fdsnws/event/1/1). |
| OpenFEMA Disaster Declarations Summaries v2 | Declared disaster context and designated recovery programs/areas | The official federal catalog lists the v2 endpoint. Some FEMA pages could not be fetched during research. Validate the current schema, update behavior, and program flags in an integration task. Declaration data is not a live hazard feed or an individual eligibility decision. [Federal catalog](https://catalog.data.gov/dataset/disaster-declarations-summaries). |
| FEMA IPAWS | Candidate expansion to weather and nonweather public alerts | NWS documentation identifies IPAWS as an additional feed requiring application for access. Current access terms must be confirmed before making it a launch dependency. [NWS alerts documentation](https://www.weather.gov/documentation/services-web-alerts). |
| 211 National Data Platform | Community service discovery | Developer portal documents APIs, including V2 search/query/export capabilities and trial registration. Data permissions, pilot coverage, costs, and permitted storage need validation. [Portal](https://apiportal.211.org/), [onboarding](https://apiportal.211.org/get-started-overview), [access permissions](https://register.211.org/Home/LogIntoApiPortal). |
| American Red Cross shelter locator | Official shelter/service discovery and a referral fallback | Public locator verified. A production API or permission to ingest its underlying data has not been established. Do not assume a public map grants unrestricted API access. The page states Red Cross shelters do not require identification; its policy must not be generalized to all providers. [Shelter locator](https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html?lv=true). |
| USAGov and official program/state pages | Find authoritative application and document-replacement rules | Use agency-specific pages and forms for actual requirements. Document replacement rules vary by issuing authority. [Disaster financial help](https://www.usa.gov/disaster-financial-help), [document replacement](https://www.usa.gov/replace-vital-documents). |
| State/local emergency management and transit agencies | Local emergency orders, services, closures, and transport status | Nationwide guidance needs jurisdiction-specific adapters or verified official referrals. Select sources using the user's location; define supported data coverage explicitly. A generic route result does not establish disaster-time road safety or transit availability. [Transit API limitations](https://developers.google.com/maps/documentation/routes/transit-route). |

Open Referral HSDS is a candidate interchange model for organizations, services, locations, and service-at-location records. Extend the internal model for prerequisites, disaster-specific rules, and verification metadata; HSDS is not itself a prerequisite planner. [HSDS overview](https://docs.openreferral.org/en/v3.3.1/hsds/overview.html).

Use official APIs directly where practical. MCP may expose the same validated adapter functions to an agent, but it is a tool interface rather than an independent source of truth. A third-party MCP server needs separate provenance, permissions, reliability, and access review.

## 5. Prerequisite reasoning and shared knowledge

### Recommended separation

1. Shared program knowledge: source-backed requirements, alternative evidence, service areas, procedures, exceptions, and effective dates.
2. Private household state: documents available, reported circumstances, application history, progress, assets, and consent.
3. Review queue: proposed knowledge changes from new official documents or user-reported discrepancies.

User reports can trigger investigation. They must not silently modify the shared rules or disclose household information to other users.

### Recommended rule representation

Represent actions, programs, proofs, required facts, providers, and outcomes using typed relationships and explicit requirement expressions:

- `all_of`: all listed requirements must be satisfied.
- `any_of`: any accepted alternative can satisfy a requirement.
- Conditional rules: a requirement applies only under a defined circumstance.
- Timing: required before submission, later verification, or before receipt of a benefit.
- Status: satisfied, missing, unknown, conflicting, or not applicable.
- Scope: jurisdiction, issuing authority, incident, program version, and effective period.

Each published requirement needs its authoritative source, supporting section or excerpt, retrieval timestamp, verification status, and effective dates where known. Do not treat the model's extraction confidence as proof of policy validity.

Illustrative rule shape, not an actual agency policy:

```text
apply_for_program = all_of(
  program_open_for_relevant_incident,
  household_in_service_area,
  any_of(accepted_document_A, accepted_document_B, authorized_alternative_process)
)
```

### Planning policy

Prioritize safety and feasibility, then time-sensitive opportunities and essential needs, then the user's preferred balance of travel, expense, effort, and benefit. Do not optimize exclusively for shortest graph path or largest potential payout.

Detect circular requirements and look for source-supported alternatives. If no verified path exists, expose the blocker and a way to contact an appropriate provider or caseworker. Support parallel actions where prerequisites allow them. Preserve evidence for why each step was chosen.

### Knowledge ingestion

Prefer structured APIs, followed by official pages and form instructions. Store a source snapshot where permitted, extract candidate rules, detect changes, validate against schemas and sample cases, and publish reviewed versions. Fetch relevant missing material on demand and cache permitted public information rather than browsing the entire web for every chat turn.

For the first implementation, curate high-priority national programs and jurisdiction-specific examples, and retrieve relevant official requirements as needed for nationwide guidance. A national resource referral does not establish verified detailed rules for every jurisdiction. Automatic policy publication remains a separate scope decision. Conflicting or inaccessible sources require an explicit uncertain state and a verified official referral or confirmation task, not invented rules.

## 6. Financial monitoring — proposal for discussion

Recommended direction: a recovery cash-flow engine, with optional account connectivity added according to implementation stage and budget.

Latest clarification: the user does not require a Flex API. The financial feature is intended for the Best FinTech App challenge, which asks for creative fintech use. The financial direction is a 14-day deterministic forecast, explicit aid timing scenarios, restricted/noncash support, and financial consequences of feasible recovery paths. The consolidated specification sets read-only Plaid Sandbox linking as an optional stretch feature. The previous question about Flex provider identity is obsolete.

| Capability | Behavior | Scope decision |
| --- | --- | --- |
| Money available now | Cash, accessible account funds, and user-confirmed balances with timestamps | Proposed core |
| Essential-expense forecast | Dated food, medication, shelter, transport, childcare, communication, and document costs | Proposed core; user can edit categories and assumptions |
| Aid lifecycle | Track identified, eligibility unknown, applied, approved, received, denied, and appeal stages | Proposed core; approval does not mean funds are available |
| Restricted and noncash aid | Show permitted-use constraints and food/shelter/voucher support separately | Proposed core; include restrictions only where sourced |
| Scenarios | Compare no new aid, delayed aid, and a stated receipt scenario | Proposed core; no invented award probability or guaranteed arrival date |
| Cost of recovery actions | Include transport, fees, deposits, and recurring obligations introduced by a proposed step | Proposed core |
| Forecast alerts | Show when essential expenses are expected to exceed accessible funds; explain assumptions and suggest relevant assistance | Proposed core; notification channel and frequency pending |
| Account connection | Optional read-only balance/transaction import through an approved provider | Pending; no requirement for users to connect an account |
| Reconciliation | Match imported transactions with manually tracked aid and spending, account for transfers, and avoid pending/posted duplicates | Required if imports are included |
| Receipt/award parsing | Propose entries from user-provided receipts or award letters for review | Pending; depends on document storage and extraction scope |
| Payment or borrowing actions | Move money, apply for credit, negotiate bills, or initiate payments | No inclusion assumed; requires a separate product decision |

Baseline forecast:

```text
projected_accessible_cash(day) = opening_accessible_cash
                             + confirmed_accessible_receipts_through_day
                             - dated_cash_outflows_through_day
```

This formula is illustrative, not a final ledger contract. Do not double-count transactions already reflected in a starting balance. Restricted benefits require category-aware allocation; credit limits are not cash; asset value is not necessarily accessible money; internal transfers are not income. Aid applications and hypothetical awards belong in separate scenarios. Unknown costs and missing balances should remain visible as uncertainty.

Example: a household has $300 cash, expects $35 per day in essential cash expenses, and has a $30 upcoming document/travel expense. With those assumptions and no new receipts, there is about 7.7 days of coverage. If a verified free meal resource reduces the cash food expense, the forecast changes. A pending aid application does not increase current funds. Real forecasts should use dated expenses rather than rely solely on a daily average.

For imported data, make source timing visible. Plaid documents differences between current/available balances, cached versus refreshed balance data, and pending-to-posted transaction transitions. Account data is not uniformly real time. Provider selection and commercial access are not decided. [Balance documentation](https://plaid.com/docs/balance/), [transaction states](https://plaid.com/docs/transactions/transactions-data/), [transaction freshness](https://support.plaid.com/hc/en-us/articles/15373384920599-Do-the-transactions-get-and-transactions-sync-endpoints-provide-real-time-data).

The model may explain a forecast or suggest a scenario. Calculation, transaction reconciliation, and ledger writes belong in tested code with explicit user corrections.

### Product idea: finances should change the recovery plan

Sophistication should come from helping the household make feasible decisions with incomplete information, including a cash-only household. Proposed capabilities:

- Today view: what resources are accessible now, what essentials are covered, and the next expected cash shortfall under visible assumptions.
- Recovery-cost awareness: show how document fees, transport, childcare, deposits, and recurring expenses affect a recommended action where costs are known. Unknown costs stay unknown.
- Scenario comparison: compare user-selected alternatives such as temporary housing options or an aid payment arriving later. Explain what causes the difference and preserve the user's priorities.
- Aid timeline: distinguish a possible program, an application in progress, a provider approval, and money actually received. Represent use restrictions and repayment obligations when applicable.
- Resource effects: show how confirmed access to meals, shelter, transport, or waived fees could reduce projected expenses. A resource suggestion alone does not prove a saving occurred; ask the user to confirm or keep it hypothetical.
- Conversational updates: let the user propose entries such as “I spent $18 on groceries” or “the aid arrived,” then show the interpreted change for correction before it affects authoritative balances.
- Actionable shortfall response: when a projected gap appears, offer relevant assistance searches, lower-cost ways to complete recovery steps, or provider-contact preparation as permitted by the chosen authority scope.

Illustrative household decision: a document-replacement trip has a known $30 cost and the household has limited cash. The agent considers a source-supported remote option or transport assistance and shows the effect of each option on the household's essential-expense coverage. It must not invent a remote option, assume unconfirmed free transport, or spend the household's money automatically.

Accepted default: prepare application answers and call scripts for user review; prioritize immediate essentials and near-term recovery in the MVP. Manual financial input is required, and Plaid Sandbox linking is optional. Document extraction is deferred by default. See the consolidated specification for the authoritative scope.

## 7. Interactive dashboard candidates

- Immediate-help card with verified contact, location, source time, and next action.
- Next-step card with why it matters, requirements, effort/cost, deadline, and fallback.
- Recovery task list with ready, blocked, waiting, completed, and skipped states.
- “I cannot do this” controls for no transport, no document, no phone, cost, access needs, and other constraints.
- Document checklist showing available evidence, missing evidence, and accepted alternatives.
- Application tracker distinguishing user-reported status from provider-confirmed status.
- Cash-flow calendar, essential-expense coverage, scenario comparison, and aid tracker.
- Source and uncertainty details available without overwhelming the main screen.
- Exportable recovery summary for the household or a helper, with deliberate selection of shared information.

Use schema-defined components rendered by the application. The agent proposes structured content and allowed actions; it does not execute arbitrary generated HTML or JavaScript. Validate proposed dashboard changes and enforce household authorization on every state mutation.

### Agent-created dashboard

The dashboard should grow from the recovery file. For a household with an urgent shelter need, start with relevant immediate help and a next action. For someone already housed, emphasize document recovery, applications, or finances according to their priorities. This is a recommendation for personalized composition, not permission to create arbitrary new interfaces.

Conceptual tool capabilities:

| Capability | User-visible effect |
| --- | --- |
| Create or update the recovery file | The household's relevant context persists and can be corrected |
| Find and attach a resource | A source-backed resource card becomes available |
| Add or revise recovery steps | The task list reflects prerequisites, alternatives, costs, and status |
| Record a question or blocker | The next interaction explains what information or help is needed |
| Record a financial event and recalculate | The money view reflects confirmed entries and revised forecasts |
| Update dashboard composition | Relevant existing components are shown in a useful order |

User changes such as marking a task done, editing a budget assumption, or selecting “I cannot do this” are meaningful inputs to the agent. A dashboard update must preserve completed work and explicit user corrections. The agent can maintain the internal file as part of the intended workflow. The accepted MVP default is user-reviewed preparation and referrals; external submissions, contacts, bookings, and financial transactions are deferred.

## 8. High-level architecture candidate

```text
Mobile-friendly dashboard and chat
                 |
      Case API and agent orchestrator
         /          |             \
 Household state  Planning and     Financial ledger
                  rule engine     and forecasts
                      |
          Shared verified program knowledge
                      |
       Source adapters and ingestion workers
```

Recommended initial shape: a modular application with a transactional database, background workers, and clear internal interfaces. A dedicated graph database or microservice deployment is not assumed. Preserve graph semantics in the rule model so storage can evolve if measured needs justify it.

Modules for later coding-agent assignments:

1. Case state, authentication/recovery, and household permissions.
2. Disaster and resource adapters, source registry, and freshness behavior.
3. Program knowledge ingestion, review tooling, and rule versioning.
4. Prerequisite planner and constraint validation.
5. Conversational orchestration, question selection, and plan revisions.
6. Dashboard component schemas and accessible user interface.
7. Financial ledger, scenarios, and any chosen import adapter.
8. Evaluation fixtures, failure behavior, operations, and deployment.

Finalize shared contracts before parallel implementation. Each later work package should state responsibilities, inputs, outputs, dependencies, acceptance criteria, and relevant failure cases. Owning files and concrete implementation contracts can be settled in those sessions. The implementation timebox is confirmed as 12 hours. Strands and Qwen-on-Akamai are confirmed; concrete frameworks, storage, model deployment, and hosting decisions are deferred.

## 8A. Strands + Qwen on Akamai — high-level responsibilities

- Strands coordinates the agent backend: initial/ongoing conversation, follow-up questions, recovery-file creation, and calls to the application's capabilities.
- Qwen on Akamai provides reasoning and proposed plans grounded in retrieved evidence.
- Application services own household state, verified resource information, prerequisite validation, financial calculations, and interactive dashboard updates.
- Durable case state lets conversation resume and keeps all access channels consistent.
- Implementation sessions will select model deployment, adapter configuration, application hosting, and language/frameworks.

Conceptual arrangement:

```text
Web dashboard / text channel
            |
Case API + Strands agent
       /            \
Validated tools     Authenticated Qwen endpoint on Akamai
       |
Case database, resource adapters, rules, financial engine
```

The stack has a documented integration reference, which later implementation sessions can assess. No deployed integration has been tested here. [Strands overview](https://strandsagents.com/docs/), [Akamai Strands/Qwen example](https://github.com/akamai-developers/vllm-on-lke), [Akamai Qwen deployment](https://techdocs.akamai.com/quick-deploy-apps/docs/qwen), [Qwen function calling](https://qwen.readthedocs.io/en/stable/framework/function_call.html).

The key product boundary is that the agent proposes and explains actions while application services enforce rules and calculate money. The high-level specification will define expected behavior; implementation sessions will validate the selected model integration against it.

## 9. Reliability, privacy, and access requirements to settle

- Keep user information outside shared knowledge; enforce case authorization on every API/tool call.
- Collect only necessary sensitive facts. Decide whether raw identity documents belong in StillHere at all.
- Define retention, deletion, encryption, access logging, and consent before handling real survivor data.
- Treat source pages and uploaded files as data, never as agent instructions. Tools validate destinations and permissions independently of model text.
- Preserve useful plans during provider or model outages; show when information is stale or has not been verified.
- Decide how account recovery works when a user loses access to email, phone, or the original device.
- Decide which content can be saved offline and whether shared-device users can opt out of local sensitive storage.
- Never label an official form submitted or a provider appointment booked without confirmed evidence.
- Define human referral versus staffed human case management. Do not promise live staffing before an operator exists.
- Define notification consent, quiet periods, and sensitive message content if SMS or push is added.

## 10. Acceptance scenarios for the final specification

The final specification should include concrete expected behavior for:

1. Mother with two children, lost home/documents, $300 cash, and immediate shelter need.
2. Same household reveals it has no car after receiving a plan.
3. Available records do not confirm a current shelter's capacity or accessibility.
4. Lost ID and birth certificate appear to require each other.
5. User is displaced across state lines and needs records from another jurisdiction.
6. No federal declaration matches the user's incident, but local resources may still exist.
7. Program rule changes or conflicting source material affect an existing plan.
8. User cannot or declines to answer an intake question.
9. Aid is approved but not received, delayed, denied, or restricted to a particular purpose.
10. A bank import arrives late or represents a pending transaction as a new posted transaction.
11. Device is shared, internet is intermittent, or the user loses account access.
12. Agent receives malicious instructions embedded in a source page or uploaded document.

Useful success measures include time to the first usable resource, number of unnecessary questions before help, source freshness, rate of feasible next steps, prerequisite correctness, successful adaptation, and correct cash-flow accounting. Chat engagement alone is not the product outcome. Numeric targets and public-use release gates remain to be agreed.

## 11. Decision ledger

| ID | Decision | Status / proposed starting point |
| --- | --- | --- |
| D01 | Delivery stage and implementation timebox? | Accepted default: demonstrable prototype, 12 dedicated hours with coding agents; real-survivor launch readiness is future scope |
| D02 | Launch geography and crisis categories? | Accepted: nationwide guidance for floods, storms/hurricanes, wildfires, and earthquakes. Detailed verified policy coverage is explicitly bounded; territorial/tribal specialization requires later validation |
| D03 | Meaning of disconnected and required channels? | Accepted: support both groups through saved/offline progress, printable summaries, and a text access path. Default to a labeled text simulator if no usable sender exists; no claim of first-time access with zero connectivity |
| D04 | Agent authority: recommend, prepare, or submit/contact on a user's behalf? | Accepted: resource discovery, case/plan updates, and application-answer/call-script preparation for user review. External commitments are deferred |
| D05 | Financial first-version scope and import approach? | Recovery cash-flow engine, manual cash/expenses/aid, 14-day scenarios, support coverage, and recovery costs. No Flex requirement; optional read-only Plaid Sandbox integration |
| D06 | Raw document uploads/vault, extraction, and retention? | Default deferred for the 12-hour prototype; document checklist and user-provided facts are sufficient |
| D07 | Direct-to-survivor product, caseworker tool, or both? | Default: direct survivor use, allowing a helper to assist; a separate multi-household caseworker console is future scope |
| D08 | Knowledge publication and review ownership? | Accepted: source-backed reviewed shared rules, household-private records, and user reports that flag discrepancies rather than rewrite policy |
| D09 | Who operates data refreshes and supports real users? | Future public-pilot responsibility; implementing team maintains demonstration sources and labels stale/unavailable information |
| D10 | Languages, accessibility, and login/account recovery? | Recommended prototype defaults: plain English, mobile/keyboard/screen-reader access, skips and corrections, and household isolation. Authentication mechanisms and production account recovery belong to implementation/pilot design |
| D11 | Preferred stack, hosting, model provider, build time, and monthly budget? | Confirmed: 12 hours, Strands Agents SDK, Qwen inference on Akamai Cloud. Detailed stack, hosting, and budget decisions deferred to implementation sessions |
| D12 | First-version program categories and catalog? | Accepted categories: urgent essentials, document recovery, aid, and finances; bounded reviewed catalog plus relevant official retrieval, with completeness limits visible |
| D13 | Definition of success and deferred capabilities? | Accepted: urgent actionable help, feasible prerequisites/alternatives, no-car replanning, persisted chat/dashboard controls, and finance updates for spending, received support, and delayed aid. No public-readiness claim |
| D14 | Live text access or prototype workflow? | Default: labeled simulator unless an already usable sender can be validated within the timebox; live delivery is not a core dependency |
| D15 | Exact Qwen model, serving interface, endpoint readiness, GPU capacity, and SDK language? | Deferred by the user to separate implementation sessions; not a blocker for the high-level specification |
| D16 | Must the Strands backend run on AWS, or is using the SDK sufficient? | No hosting requirement established. User reports Strands-related credits; entitlement and deployment decisions deferred |
| D17 | Relationship between agent, user file, and dashboard? | Confirmed: agent is the central backend workflow and uses tools to create/maintain the user file/dashboard |
| D18 | First-use entry experience? | Confirmed direction: a short general multiple-choice selection phase before chat. Exact questions, urgent-help bypass, and skip behavior are proposed |
| D19 | Can users act through both conversation and dashboard controls? | Confirmed: both; changes affect the same recovery file and relevant plan/financial views |
| D20 | Is a specific fintech provider required? | Confirmed: no Flex-specific requirement. The goal is a creative fintech capability for the challenge |
| D21 | Ongoing monitoring and welfare follow-up? | Accepted MVP scope: optional scheduled check-ins, timestamped last-shared location, and a simulated human follow-up queue. No committed response team; live outreach, field response, and detailed partner discovery are later pilot work. Integrated into the project specification |

## 12. Exit criteria for discovery

Discovery has been consolidated into `docs/project-specification.md`. Product scope is defined there. The implementation constraints are a 12-hour MVP and Strands with Qwen on Akamai; concrete technical choices belong to later sessions. Real-world operating responsibilities are future work outside the prototype's purpose.

The user subsequently approved adding optional check-ins, last-shared location, and simulated human follow-up to the specification. That scope is integrated; detailed response partnerships remain later pilot work and do not block implementation planning.

Remaining external dependencies must be recorded as validation tasks with owners and usable fallback behavior. The final document should make accepted requirements, engineering choices, future scope, and unresolved external dependencies distinguishable so implementing agents do not have to invent product policy.
