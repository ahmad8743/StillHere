# StillHere — Infrastructure direction

Updated: October 10, 2026. This records the user's revised infrastructure requirements and the reference checkout; executable component boundaries remain in [contracts and progress](contracts-and-progress.md).

## Confirmed arrangement

| Responsibility | Location / owner |
| --- | --- |
| Web UI, case API, Strands runtime, tools, finance/planner code, and later workers | Akamai Cloud application hosting; P1 assembles the backend, P2 supplies UI/finance |
| Durable household cases, audit events, and later chat/knowledge data | Akamai-hosted application storage; current local C01 implementation uses SQLite |
| Model inference | AWS Bedrock, called by the backend through the Strands Agents SDK |
| Model and hosting credentials | Backend/deployment configuration; never part of client requests or shared case snapshots |

Strands is the SDK running our agent loop and dispatching registered tools. Bedrock supplies the language model. The frontend calls our authorized case API. Tools call application services, and `CaseService` owns validated durable writes. The SDK and model provider do not own household authorization or financial calculations. [Strands Bedrock provider documentation](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

The exact Bedrock model or inference profile, AWS region, Akamai runtime, and deployed storage setup are not selected yet. These choices must preserve the existing case/version/event contracts and durable state across restarts. A provider or hosting choice alone does not require a change to contract `0.1`.

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

The user is obtaining Akamai and AWS access. No credentials are needed for the retained C01 case/intake tests or reference review.

Before the live C02 proof, supply an AWS credential configuration with Bedrock invocation permission, an explicit region, and an accessible tool-capable model/inference-profile ID. Temporary AWS credentials also need their session token. The implementation should use the SDK credential chain and explicit model/region settings. [Strands credential and model configuration](https://strandsagents.com/docs/user-guide/sdk/model-providers/amazon-bedrock/).

Akamai account access and the selected service configuration are needed for deployment. A workshop inference key is separate from Bedrock access. Keep local credential values in ignored `.env`/`.env.*` files or external credential configuration; only blank `.env.example` templates may be committed.

The uncommitted first C02 attempt was removed, retaining the committed case and intake slices at `0d56429`. C02 returns to `NOT_STARTED`. Its scope remains one Bedrock model, durable user/assistant turns, and two registered tools: read the authorized case and submit a validated fact correction. Verify access, turn replay, case conflicts, and provider failure with bounded model/tool usage. Live model/tool verification awaits AWS access; Akamai deployment follows as a separate slice.
