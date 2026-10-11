# StillHere — Infrastructure direction

Updated: October 11, 2026. This records the user's revised infrastructure requirements and the reference checkout; executable component boundaries remain in [contracts and progress](contracts-and-progress.md).

## Confirmed arrangement

| Responsibility | Location / owner |
| --- | --- |
| Web UI, case API, Strands runtime, tools, finance/planner code, and later workers | Akamai Cloud application hosting; P1 assembles the backend, P2 supplies UI/finance |
| Durable household cases, audit events, and later chat/knowledge data | Akamai-hosted application storage; current local C01 implementation uses SQLite |
| Model inference | AWS Bedrock, called by the backend through the Strands Agents SDK |
| Model and hosting credentials | Backend/deployment configuration; never part of client requests or shared case snapshots |

Strands is the SDK running our agent loop and dispatching registered tools. Bedrock supplies the language model. The integration target is for the frontend to call our authorized case API; the current `frontend/` prototype uses browser-local fixtures and canned conversations. Tools call application services, and `CaseService` owns validated durable writes. The SDK and model provider do not own household authorization or financial calculations. [Strands Bedrock provider documentation](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

The user selected Claude Sonnet 4.5 as the current working Bedrock model and previously confirmed source region `us-east-2`. The working model/profile ID remains in private configuration; it is not retained in safe diagnostics. Akamai runtime and deployed storage are not selected yet. These choices must preserve the existing case/version/event contracts and durable state across restarts. A provider or hosting choice alone does not require a change to contract `0.1`.

The [Strands capability review](strands-capabilities.md) maps sessions, context management, memory, tools, and other SDK features to the planned components. It records recommendations separately from implementation status.

## Workshop reference

- Upstream: [akamai-developers/akamai-workshop-hackmidwest](https://github.com/akamai-developers/akamai-workshop-hackmidwest).
- Local checkout: `.references/akamai-workshop-hackmidwest/`.
- Reviewed revision: `e362ae25ea54a5ee33fa11f6265d15bc1705dca3` (shallow clone).
- Git ignores the entire `/.references/` directory, including the nested repository and any local configuration added there. A fresh StillHere checkout does not contain this reference.

The workshop's `docs/cloud.md` explains runtime/storage choices, `docs/03_body.md` shows Linode deployment, and `docs/build.md` explains adapting an existing application. Its code guide demonstrates tool registration. These are reference materials for a later Akamai deployment slice.

The workshop starter uses its own inference endpoint, `/chat` API, and persistence conventions. StillHere uses Bedrock and retains its versioned `/v1` API, scoped bearer sessions, atomic command processing, and private household records. Any adopted deployment configuration must support these boundaries and persistent application data. No workshop code, dependencies, schemas, or deployment scripts have been incorporated or executed.

To recreate the reference checkout from the StillHere root:

```sh
git clone --depth 1 https://github.com/akamai-developers/akamai-workshop-hackmidwest.git .references/akamai-workshop-hackmidwest
```

This fetches the upstream default branch at the time of cloning; record the new revision before relying on changes.

## Credentials and next slice

The confirmed default-path user-run live Bedrock proof passes at 6.072 seconds with two tool calls, a saved fact/reply and replay verification. A subsequent agent smoke passes at 18.681 seconds with one tool call; the safe log omits its mode/model identity. C01-facing agent adapters and the bounded C02 runtime are READY_FOR_INTEGRATION. No credentials are needed for case/intake tests or the real-SDK scripted-model checks. Akamai deployment access remains a separate gate. [Agent handoff](agent-integration.md).

Keep the working AWS credential configuration, explicit region, and model/inference-profile ID for this slice. Temporary AWS credentials also need their session token. The implementation uses the SDK credential chain and explicit model/region settings. [Strands credential and model configuration](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

Akamai account access and the selected service configuration are needed for deployment. A workshop inference key is separate from Bedrock access. Keep local credential values in ignored `.env`/`.env.*` files or external credential configuration; only blank `.env.example` templates may be committed.

The previous Qwen attempt was removed when the architecture changed. Its replacement is the pinned Strands/Bedrock runtime at `backend/stillhere/agent/`, with two default tools, opt-in intake/incident/resource/rule/source/review tools, saved turns, replay/conflicts, run claims and usage limits. The bounded runtime and C01-facing adapters are READY_FOR_INTEGRATION after the live proof. C03 public NWS/USGS/OpenFEMA adapters and their agent tool are also ready, with synthetic live public-source checks and offline SDK/persistence evidence. These sources require no new credentials. Full C02 readiness still requires later tools/output contracts. All five bounded C04 slices are ready for integration, including official fetching, separate public candidates/discrepancies and local manual version publication. The new knowledge failure branch passes live at 13.569 seconds; the national strict-fetch model/reply/replay proof now passes at 13.265 seconds; Colorado candidate extraction and shared review remain pending; policy coverage stays partial. [Fetch/review handoff](knowledge-review-integration.md). The user-run rules/resources model proofs pass at 14.992/18.535 seconds with mode-labeled safe logs. The rule catalog adds no provider credentials or network requests. User-run `agent.smoke --rules` verifies the new model/tool path; new safe logs identify its mode. [Rule handoff](program-rules-integration.md). C09 is outside this chat's work. [C04 handoff](resource-integration.md). Akamai deployment follows separately; no workshop deployment code has been incorporated. [C03 handoff](incident-integration.md).
