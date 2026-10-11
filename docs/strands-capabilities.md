# Strands capabilities and StillHere fit

Reviewed October 10, 2026 through the Strands website in the browser, including its Python documentation. The broad capability map remains research and proposed sequencing. The C01-facing read/fact/intake adapters, bounded C02 runtime and C03 incident adapters/tool are READY_FOR_INTEGRATION with Strands `1.59.0`. The default live Bedrock proof passed with user-selected Claude Sonnet 4.5; public C03 source checks pass separately with synthetic geography. All five bounded C04 slices are READY_FOR_INTEGRATION: referrals, published rule graphs, bounded official fetching, separate candidate/discrepancy submissions and local manual publication with immutable history. Offline SDK/workflow evidence passes; prior rules/referrals live proofs pass at 14.992/18.535 seconds. The new knowledge failure/discrepancy branch passes live at 13.569 seconds; the national strict-fetch model/reply/replay proof now passes at 13.265 seconds; Colorado live candidate extraction remains pending; policy coverage remains partial. C05 is IN_PROGRESS with evaluation, saved-plan revision and task-report slices READY_FOR_INTEGRATION; live planner/workflow proofs remain pending. The broader C02 component remains IN_PROGRESS for the later tools/output contracts below. The public boundary remains `0.1`. C09 is outside this chat's current work. See the [implementation handoff](agent-integration.md), [C03 handoff](incident-integration.md), [C04 referral handoff](resource-integration.md), [C04 rules handoff](program-rules-integration.md), and [C04 fetch/review handoff](knowledge-review-integration.md).

## Which part of Strands we need

The site presents a complete Strands harness alongside the SDK used to assemble an agent. The Python SDK supplies the agent loop and configurable tools, sessions, memory, plugins, and interventions. StillHere's existing case service fits the SDK approach: select our model and register our own application capabilities. [SDK overview](https://strandsagents.com/docs/user-guide/sdk/).

Strands runs as a library in our backend process. It can use Bedrock without requiring an AWS-hosted application, database, or scheduler. Keep the application and durable data on Akamai, as confirmed in [infrastructure direction](infrastructure-direction.md). [Framework responsibilities](https://strandsagents.com/docs/user-guide/migrate/choosing-an-agent-foundation/).

## Capability map

The fit and sequencing columns are recommendations for StillHere. Links identify the documented SDK capability.

| Capability | Contribution to StillHere | Sequence |
| --- | --- | --- |
| [Bedrock provider and agent loop](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/) | C02: coordinate user requests, model decisions, tool results, and replies. Configure the selected model and region explicitly. | First agent slice |
| [Custom tools and execution context](https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/) | C02: add case/source/planner/finance adapters through registered functions and explicit schemas. Supply authenticated context from the backend outside model arguments. | Case read and fact correction first; other tools later |
| [Session persistence](https://strandsagents.com/docs/user-guide/sdk/agents/session-management/) | C02/C09: restore conversation history and agent state after a restart using local or custom storage. Bind conversation identity to authorized household/case access. | Durable chat first |
| [Conversation management](https://strandsagents.com/docs/user-guide/sdk/agents/conversation-management/) | C02: keep recent conversation within context limits; optionally summarize older turns. Refresh important case facts from the current snapshot. | Bounded recent history first; summaries later |
| [Long-term memory](https://strandsagents.com/docs/user-guide/sdk/memory/overview/) | C02: retrieve preferences or earlier decisions across conversations through a configured store. Custom storage can keep that data on Akamai. | Separate later memory slice |
| [MCP tools](https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/) | C03/C04: connect external retrieval services where useful. Our adapters still normalize records, attribution, freshness, and failures. | Source/knowledge slices |
| [Structured output](https://strandsagents.com/docs/user-guide/sdk/agents/structured-output/) | C02/C10: return schema-shaped questions or component proposals. The backend still validates shared contracts and referenced records before publishing. | Introduce with the relevant output contract |
| [Streaming](https://strandsagents.com/docs/user-guide/sdk/streaming/) | C09: show reply text and tool progress while work runs. P2 needs an agreed transport and clear pending/final states. | Chat UI integration |
| [Hooks](https://strandsagents.com/docs/user-guide/sdk/agents/hooks/) and [human input](https://strandsagents.com/docs/user-guide/sdk/agents/interventions/human-in-the-loop/) | C02/C07: intercept execution, enforce tool limits, and pause/resume where explicit permission is required. App consent commands remain authoritative. | Minimal execution hooks first; consent workflow later |
| [Lifecycle limits](https://strandsagents.com/docs/user-guide/sdk/agents/lifecycle-controls/) and [observability](https://strandsagents.com/docs/user-guide/sdk/observability-evaluation/observability/) | C02/C16: bound agent work, handle cancellation/failure, and inspect model/tool latency and usage. | Small usage budgets and safe metrics first |
| [Evaluation SDK](https://strandsagents.com/docs/user-guide/evals-sdk/quickstart/) | C16: score synthetic recovery conversations and tool trajectories, such as correction handling or useful follow-up questions. Deterministic contract/access/finance checks remain required. | Later acceptance work; model judges add inference calls |
| [Multiple-agent patterns](https://strandsagents.com/docs/user-guide/sdk/) | Later specialized research workflows could use agents as tools, graphs, or swarms. The current specification needs one coordinating runtime agent. | Defer until a specific workflow needs it |

The Bedrock provider also supports prompt caching, guardrails, and model-dependent multimodal input. Caching could help repeated prompts/tool definitions once the model is selected. Multimodal input does not change the MVP's deferred document-upload scope. [Bedrock features](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

## What “memory” means here

Memory supplies saved context to model requests; it is not a change to the model's trained weights.

| Kind | Example | Proposed owner |
| --- | --- | --- |
| Conversation history | What the household and assistant said yesterday | Application-owned durable turns, connected to the SDK's session interface where appropriate |
| Working context | Recent turns and a concise view of the current case sent with this request | Agent runtime and conversation manager |
| Long-term conversational knowledge | A reported preference for short explanations or a previous decision | Later case-scoped memory store and retrieval adapter |
| Structured recovery records | Current transport constraints, completed actions, money, and explicit consent | Existing case service and the owning deterministic modules |

Session persistence saves the conversation; context management trims or summarizes what the model sees; long-term memory retrieves knowledge across sessions without replaying every conversation. These are distinct mechanisms. [Memory overview](https://strandsagents.com/docs/user-guide/sdk/memory/overview/).

The documented `MemoryManager` can search on demand, inject relevant entries before a model request, and optionally save memories through a tool or automatic extraction. Writes are opt-in. A custom `MemoryStore` can be read-only and backed by our own application storage. [Memory controls](https://strandsagents.com/docs/user-guide/sdk/memory/managing-memory/).

For StillHere, start with durable turns plus current case facts. Later memory entries should retain origin and time, be scoped by backend authorization, and reflect corrections or deletion. A conversational summary must not override a newer case record. For example, if yesterday's chat said “no car” but today's accepted correction says transport is available, use today's case state. Household-private context and shared reviewed program knowledge need separate access scopes.

Use explicit validated case commands for facts and consent. An automatic memory extractor must not publish program rules, change financial records, or turn inferred information into confirmed case facts. Search failures can omit injected context, and extraction can retry duplicate writes; these documented behaviors make memory unsuitable as the authoritative write path. [Memory behavior and custom stores](https://strandsagents.com/docs/user-guide/sdk/memory/managing-memory/).

The [AgentCore Memory integration](https://strandsagents.com/docs/integrations/session-managers/agentcore-memory/) offers managed conversation persistence, preferences, facts, and summaries through an additional AWS service. Using it would add AWS memory storage to our architecture. An Akamai-backed custom store follows the current storage direction.

## Planned tool inventory

This inventory covers the [application's conceptual tools](project-specification.md#conceptual-tool-contract), [command contracts and component ownership](contracts-and-progress.md), and [finance tool responsibilities](finance-design.md#agent-tool-responsibilities). Names below are internal registry names, not new public command types. Read/fact/intake, C03 incident adapters, all five C04 tools and all three bounded C05 tools are implemented with shared schemas; other agent/domain adapters remain planned. P2's browser finance and chat prototypes exist in `frontend/`, with C08/C09 `IN_PROGRESS`; their finance agent tools and frontend/backend integration are still pending. Default registration contains read/fact tools, with intake, incident retrieval and reviewed resource referrals, rule lookup, public source/review and read-only planner groups opt-in. Review enables its required fetch tool.

Strands supplies the callable-tool interface and orchestration. Our services supply disaster lookup, recovery rules, planning, finance calculations, permissions, and persistence. We will use the following specific SDK features:

| Feature used below | Planned use |
| --- | --- |
| **Custom tool** | Python `@tool(context=True)` with typed arguments and the SDK's explicit `inputSchema={"json": ...}` override where needed (verified against pinned `1.59.0`). `ToolContext.invocation_state` carries backend-supplied session/case authority and turn context outside model-selected arguments. The adapter calls the owning application service. [Custom tools](https://strandsagents.com/docs/user-guide/sdk/tools/custom-tools/). |
| **Consent interruption** | Strands human-in-the-loop interrupt/resume when an action lacks required explicit consent. Resume only after the application accepts the authenticated user's consent action; an LLM-generated permission field cannot authorize it. Existing valid consent does not require another prompt. [Human input](https://strandsagents.com/docs/user-guide/sdk/agents/interventions/human-in-the-loop/). |
| **Memory search** | A later `MemoryManager` registers its documented `search_memory` tool against a custom, initially read-only `MemoryStore` on Akamai. The backend fixes household/case scope. [Memory controls](https://strandsagents.com/docs/user-guide/sdk/memory/managing-memory/). |

All custom tools also share `BeforeToolCallEvent` / `AfterToolCallEvent` hooks for execution limits, checks, and safe result/latency reporting. Hooks supplement the application's authorization and validation. They do not replace them. [Hooks](https://strandsagents.com/docs/user-guide/sdk/agents/hooks/).

### Case and intake — C01/C02/C09, P1 adapters

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `read_case` (implemented) | Read the latest authorized `CaseSnapshot`, including unknown/pending states. Backend context fixes which household/case may be read. | Custom tool | First C02 slice |
| `correct_fact` (implemented) | Submit `fact.correct` with `FactCorrectionPayload`; C01 derives provenance, checks the version, audits the change, and marks affected derived outputs pending. Facts cannot grant consent or alter the ledger. | Custom tool | First C02 slice |
| `submit_intake` (implemented, opt-in) | Submit `intake.submit` using the existing `IntakeSelections` vocabulary. Partial answers remain valid; selections do not imply household headcounts, financial amounts, or sharing permission. | Custom tool | Later intake/chat integration |

### Incident, resources, and reviewed knowledge — C03/C04, P1

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `get_incident_context` (implemented, opt-in) | NWS/USGS/OpenFEMA facade using backend-reported current/damaged geography; CaseService commits typed context/source attribution with version/run/replay checks. Missing geography, no match, provider failure, truncation and stale inputs remain distinct. A declaration does not establish household eligibility. [Handoff](incident-integration.md). | Custom tool | C03 READY_FOR_INTEGRATION |
| `find_resources` (implemented, opt-in) | Select seeded reviewed national/Colorado referral routes from backend-reported needs and current/damaged geography. CaseService commits the typed referrals/source times with replay, run/version checks and stale-input handling; capacity, eligibility and requirements remain unknown. Colorado 211 is a public contact referral only; directory API access remains pending. [Handoff](resource-integration.md). | Custom tool | C04 referral slice READY_FOR_INTEGRATION; bounded C04 READY_FOR_INTEGRATION |
| `retrieve_program_rules` (implemented, opt-in) | Read partial published Colorado state-ID renewal/proof-option references with source-attributed AND/OR online/office paths. Program/optional exact version are model arguments; explicit case document issuer and time come from backend. Unknown/conflicting/stale/no-match/failure states remain distinct; no prerequisite evaluation, publication or domain writes. [Handoff](program-rules-integration.md). | Custom tool | C04 rule slice READY_FOR_INTEGRATION; bounded C04 READY_FOR_INTEGRATION |
| `fetch_official_source` (implemented, opt-in) | Fetch one of five approved public government source IDs (four DMV plus national USAGov guidance) with byte/text/time/redirect limits, unreviewed hashed receipts and honest seeded/cached failure fallback. URLs and authority come from backend. [Handoff](knowledge-review-integration.md). | Custom tool | C04 fetch slice READY_FOR_INTEGRATION; national live model/fetch/reply/replay verified |
| `report_rule_discrepancy` (implemented, opt-in) | Submit a known public discrepancy reason and backend-selected source evidence, or a failed-source report. CaseService atomically stores a public record/private replay link; no policy or household domain changes. | Custom tool | C04 submission slice READY_FOR_INTEGRATION; failure branch live-verified; extraction pending |
| `propose_rule_candidate` (implemented, opt-in) | Submit allowlisted requirement keys/AND-OR relationship with a fresh same-turn public receipt and bounded evidence offsets. CaseService queues manual review; no free-text household payload or publication authority. | Custom tool | C04 submission slice READY_FOR_INTEGRATION; live candidate extraction pending |

Each external adapter uses a documented API where available. Strands `MCPClient` is an optional replacement for an adapter's transport if we select an MCP service; it is not required to implement these tools. Preserve the same application schemas, source checks, and access rules across either transport. [MCP integration](https://strandsagents.com/docs/user-guide/sdk/tools/mcp-tools/).

### Recovery planning and application preparation — C05/C06, P1

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `evaluate_recovery_options` (implemented, opt-in) | Read-only deterministic AND/OR evaluation against exact Boolean case availability/completion facts and published rules. Return provisional/blocked paths, necessary blockers/questions, sourced OR/sibling alternatives, explicit access constraints and null costs. Partial coverage cannot establish full feasibility or eligibility. [Handoff](planner-integration.md). | Custom tool | First C05 slice READY_FOR_INTEGRATION; full C05 IN_PROGRESS |
| `revise_recovery_plan` (implemented, opt-in) | CaseService recomputes published requirements and atomically saves a scoped plan revision, sources/version/audit; preserve completed/skipped/removed work and reject stale/deadline/conflict inputs. Return a bounded `RecoveryMutationResult`; no public `plan.update` command. | Custom tool | C05 revision slice READY_FOR_INTEGRATION |
| `update_task` (implemented, opt-in) | Submit `task.update` for explicit completion/skipping/inability or resolution; retain user-report history and timestamps, immediately reassess the affected route and mark plan pending. No eligibility, evidence, facts, money or consent inference. | Custom tool | C05 task-report slice READY_FOR_INTEGRATION |
| `prepare_application` | Prepare draft answers, evidence checklists, or call scripts from scoped facts and sources. Leave unknown answers blank and retain evidence references. Agree the draft-result/commit schema before storing it; no external submission occurs. | Custom tool | C06 |
| `update_application` | Submit `application.update` for a user-reported stage, correspondence, or evidence change; revise the next step without claiming agency approval. | Custom tool | C06 |

Where the model proposes a draft or component structure, use `structured_output_model` with an agreed Pydantic schema. That feature shapes and validates the model's response; application validators still check facts, sources, references, and allowed transitions. It does not implement the planner or make a proposal authoritative. [Structured output](https://strandsagents.com/docs/user-guide/sdk/agents/structured-output/).

### Finance and dashboard — C08/C10, P2 domain module/UI and P1 adapters/commit

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `read_financial_summary` | Read necessary balances, commitments, aid/support states, freshness, and uncertainties from the authorized case. Return no bank credentials or provider tokens. | Custom tool | C08 |
| `record_financial_update` | Submit typed `finance.update`; delegate validation/reconciliation to P2's pure `apply_financial_update`. C01 commits an accepted result once. Ambiguous entries return clarification rather than invented totals. | Custom tool | C08 |
| `set_financial_scenario` | Submit `scenario.set` with explicit dated hypothetical changes or alternative action IDs. Store scenario assumptions without changing actual accessible money. | Custom tool | C08 |
| `calculate_forecast` | Delegate to P2's pure `forecast_finances` for the fixed 14-day baseline, gaps, assumptions, and warnings. P1 validates the input case version before committing a derived result. | Custom tool | C08 |
| `compare_financial_scenarios` | Use the same `forecast_finances` operation with up to three scenarios. Compare hypothetical outcomes without posting receipts or overwriting the actual ledger. | Custom tool | C08 |
| `evaluate_action_costs` | Use `forecast_finances` with dated costs for feasible planner alternatives. Return financial consequences and unknown-cost warnings; the model does not perform authoritative arithmetic. | Custom tool | C05/C08 integration |
| `publish_dashboard_components` | Publish allowlisted shared component descriptors referencing persisted case records and current computed results, including financial components. Validate the descriptor/commit schema before enabling it; no generated executable UI code. | Custom tool; structured output for model-proposed descriptors | C02/C10 integration |

The three calculation tools are purpose-specific adapters to **one** finance operation, not three calculation engines. Financial-dashboard publication uses `publish_dashboard_components`; it does not need a separate tool or finance implementation. Finance retains its framework-free contract.

### Check-ins and shared location — C07/C11, P1 engine/adapters and P2 controls

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `read_check_in_status` | Read the household's schedule, last report and observation/receipt times, and simulated review status. An overdue report means condition unknown; it does not prove distress or human response. | Custom tool | C07 |
| `schedule_check_in` | Submit `check_in.enroll` after explicit opt-in with agreed due time, IANA time zone, grace period, and simulated channel preference. C07 creates stable occurrences; the SDK does not run the clock. | Custom tool + consent interruption when needed | C07/C11 |
| `record_check_in_reply` | Submit `check_in.reply` for `okay_for_now`, `need_help`, or `check_later`; the latter requires an explicitly selected next due time. Preserve report/receipt times; a reply does not silently close assigned review. | Custom tool | C07 |
| `pause_check_ins` | Submit the user's explicit `check_in.pause` action to cancel future pending attempts. An already open review remains visible. | Custom tool | C07/C11 |
| `request_help` | Submit `help.request`, show official urgent-help directions, and create a simulated review request even without check-in enrollment. Do not delay urgent directions for a consent interruption. | Custom tool | C07 |
| `share_location` | Submit `location.share` after explicit sharing permission, using an entered place or one-time device fix with observation time and optional accuracy. The frontend supplies the fix; Strands supplies neither geolocation nor background tracking. | Custom tool + consent interruption when needed | C07/C11 |
| `clear_shared_location` | Submit the user's explicit `location.clear` action to remove active shared-location access/projection while preserving unrelated residence facts. | Custom tool | C07/C11 |

All reminder/contact events remain `simulation: true`. No tool sends a real welfare SMS, places a call, dispatches help, or promises active human response. Consent enforcement belongs to C01/C07 and the authenticated controls, including direct UI use without the agent.

### Conversational memory — separate later C02 slice

| Planned tool | Result and contract boundary | Strands feature | Slice |
| --- | --- | --- | --- |
| `search_memory` | Retrieve scoped conversational preferences or earlier decisions with origin/time from an Akamai-backed store. Accepted current case facts override stale memories. Corrections/deletion must affect retrieval. | Memory search: SDK-provided tool through `MemoryManager` | Later memory slice, after durable chat |

We will not register a generic `add_memory` tool or enable automatic extraction in the first agent or first memory slice. Initially, an application-owned projection can populate the read-only store from accepted conversation/case records. A later write/extraction design needs its own agreed schema, correction/deletion handling, and inference budget. Facts, money, consent, and published policy continue through their explicit authoritative services.

### Required operations outside the household agent's tool registry

These complete the application's capabilities but run through backend services, role-scoped controls, or UI projections. They do not need to be callable by the household's model.

| Operation | Contract/component and execution boundary | Strands feature used |
| --- | --- | --- |
| Create/resume a case | C01: existing `POST /v1/cases` and scoped read establish case identity/time zone before agent execution. Resume the conversation separately from the case snapshot. | No creation tool required; SDK session persistence restores agent history, and `read_case` refreshes current facts. |
| Accept a chat message / ask a follow-up | C02/C09: `conversation.message` is the entry point, with persisted queued/running/complete/failed turn state and replay protection. Structured questions/choices require the shared output contract. | `Agent` + `BedrockModel`, session persistence, conversation manager, and streaming; `structured_output_model` for agreed question/choice shapes. No recursive message tool. |
| Process due check-ins | C07: backend scheduler/demo clock advances stable occurrences, records simulated attempts, and creates overdue/unknown review once. It runs independently of chat/model availability. | None; an application scheduler and deterministic check-in engine. |
| Read/acknowledge/update the follow-up queue | C12: operator-only projection and `follow_up.acknowledge` / `follow_up.record` commands record authenticated assignment, simulated attempts/outcomes, unresolved needs, and next actions. Operator access does not expose the full household ledger. | None for the MVP operator controls. Do not register these tools in the household agent or let model arguments select operator authority. |
| Review/publish program-rule candidates | C04: implemented local OS/database-authorized CLI validates evidence/graphs and atomically publishes a new immutable version from separate public candidate tables. Household tools cannot approve; deployed operator provisioning remains C01 work. [Handoff](knowledge-review-integration.md). | None for approval/publication; the two candidate tools above use custom tools only to submit review material. |
| Replay offline commands | C13: existing command types, original event IDs/times, ordered replay, visible conflicts, and household-scoped cache/erase. | None; C01 replay semantics remain authoritative, including commands originally proposed by tools. |
| Render the text simulator | C14: numbered synthetic inputs use the same commands/case and produce concise text. | Reuse the C02 runtime if conversational input needs it; no SMS/contact tool or new command types. |
| Render the printable summary | C15: user-selected snapshot projection; finance/location included only when selected. | None; deterministic UI/export rendering from accepted records. |
| Link/import/disconnect a test bank account, if selected | O01: optional user-initiated Plaid Sandbox UI/private backend; normalize imported records into C08's financial update path. Tokens remain outside model context. | None required; backend provider adapters and the existing finance service. Optional, not a core tool dependency. |

### Register tools gradually

Only `read_case` and `correct_fact` belong in the first C02 allowlist. Add later groups in bounded slices after their domain services and shared schemas are ready; the inventory is not a request to enable all tools at once. Register `search_memory` only in its separate memory slice because attaching a memory manager can add that tool automatically.

Each registry entry records its name, description, argument/result schemas, callable, permitted role, read/write classification, component owner, and execution budget. Tool arguments express domain intent. Backend `ToolContext` supplies authorization and stable turn/child-event identity; SDK tool-call IDs or model-supplied case/channel/consent fields cannot supply authority. Writes use C01's command/result envelopes or an agreed internal derived-result commit path, never direct database writes. Serialize case mutations and reconcile version conflicts rather than racing two writes from the same snapshot.

Before enabling each adapter, verify contract-shape validation, scoped access, relevant unknown/provider-failure behavior, and replay for durable effects. Keep future payloads behind the existing contract-review gate rather than inventing extra public command types in this inventory. The public `0.1` vocabulary and P2 module ownership remain unchanged.

## Integration constraints and next slice

1. Keep `CaseService` responsible for session authority, atomic writes, stable event identities, version conflicts, and audit history. SDK session IDs and SDK snapshots are internal agent state, separate from our bearer sessions and `CaseSnapshot` contract. SDK session managers do not provide distributed locks. [Session concurrency](https://strandsagents.com/docs/user-guide/sdk/agents/session-management/#sessions-agents-and-concurrency).
2. Derive tool and output schemas from the shared contracts. Model output still requires application validation. Bedrock strict tool schemas have restrictions, so verify compatibility instead of changing public payloads to match a provider. [Bedrock schema options](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).
3. Configure loop/token limits, per-model output caps, timeouts, and bounded retries. SDK token limits are checked between loop iterations and can overshoot during a call; cancellation does not undo an accepted case command. [Lifecycle behavior](https://strandsagents.com/docs/user-guide/sdk/agents/lifecycle-controls/).
4. Pin and verify the Python SDK release before selecting APIs. The newer context-strategy API is marked experimental; documented sliding-window and summarizing conversation managers offer a simpler starting point. [Context API status](https://strandsagents.com/docs/user-guide/sdk/context-management/), [version policy](https://strandsagents.com/docs/user-guide/sdk/versioning-and-support/).
5. Keep the [bounded first C02 slice](contracts-and-progress.md#c02-first-slice-and-tool-extensions--ready-for-integration) bounded: one Bedrock model, durable turns, current scoped case context, two default application tools with separately opt-in intake/incident/resource/rule/source/review adapters, failure/replay checks, and usage limits. A memory manager can automatically register a search tool and extraction can add model calls, so introduce those features in a later slice with explicit tool and cost budgets. [Memory configuration](https://strandsagents.com/docs/user-guide/sdk/memory/managing-memory/).

The implemented adapters and real-SDK scripted-model checks require no credentials. Live C02 verification needs accessible Bedrock model/region and AWS credentials in the private `.env.local` or credential chain. Deployment still needs Akamai access. [Configuration and live proof](agent-integration.md#run-locally-and-configure-bedrock).

C05's first deterministic read-only prerequisite/constraint planner is now
READY_FOR_INTEGRATION, using current scoped Boolean facts and published rules
while retaining unknowns. Full C05 stays IN_PROGRESS for deeper evidence/dependency links, trusted agency
confirmations and dated costs; the live Sonnet/planner/workflow proofs remain pending. All five
bounded C04 slices reached readiness with 186 non-HTTP checks (24 referral,
28 rule, 34 fetch/review and 16 real-SDK checks). That full 191-check discovery retained
five host loopback-bind errors. Prior rules/resources live proofs pass. The new user-run `--knowledge` proof
passes its failure/discrepancy branch at 13.569 seconds with unavailable retrieval;
national fetching now passes the strict live proof. Colorado live candidate
extraction and P2 boundary review remain separate gates. The user also reports the offline knowledge workflow passed. Direct backend GET currently fails DNS here. The
[fetch/review handoff](knowledge-review-integration.md) gives the user checklist
and marks policy coverage/eligibility/fees/effective dates unknown.

A credential-free source diagnostic now repeats the approved public fetch and
reports safe failure categories/HTTP status. Six new checks pass within a
66-check focused run at the diagnostic milestone; that discovery contained 197 tests. The user-run smoke
historical failure reason is unavailable; both Codex probes currently report DNS
failure. [Diagnostic guide](knowledge-review-integration.md#diagnose-an-unavailable-public-source).


The user requires a working C04 new-information fetch before C05. Approved
fetch-only national source `source_usagov_lost_documents` and strict `--fetch`
smoke now exercise fresh text, source-backed saved reply, unchanged domains and
replay. There is no seeded fallback or Colorado review/publication scope for this
source. Web-reader access succeeds; direct Codex backend DNS failures and the
user-terminal/live-model evidence remain distinct. The latter now passes at
13.265 seconds with one tool call and available retrieval; C05's successful-fetch
prerequisite is satisfied and its read-only first slice is now ready. [Working example](knowledge-review-integration.md#working-live-fetch-example--verified).

Current strict-fetch validation: 203 non-HTTP checks and 17 real-SDK checks
pass; discovery contains 208 tests. The new example has ten focused checks.
User-terminal live success now passes, clearing the prerequisite before C05.

C05 validation adds 28 planner and two real-SDK checks; the focused planner/rule/SDK
run passes 75 checks. Later shared discovery runs 295 checks with 290 passes
(including 57 concurrent finance checks and 19 real-SDK checks) and five existing
HTTP loopback-bind errors. The new opt-in flag is
`STILLHERE_AGENT_ENABLE_PLANNER=true`; it adds evaluation independently of rule
lookup. No saved plan/task/finance or policy writes occur. Live planner proof and
P2 review remain separate. [Contracts, semantics and user tests](planner-integration.md).

Two additional C05 slices are now READY_FOR_INTEGRATION: CaseService saved-plan
revision and task reporting/reassessment. Independent flags are
`STILLHERE_AGENT_ENABLE_PLAN_REVISION=true` and `STILLHERE_AGENT_ENABLE_TASKS=true`.
New writes expose compact model summaries while full data/audit remain in C01.
108 focused checks and all 325 non-HTTP checks pass among 330 discovered, including
21 real-SDK checks. Live `--plan`, P2 review and broader C05 gates remain pending.
[Updated handoff](planner-integration.md#saved-plan-revision--second-slice-ready-for-integration).
