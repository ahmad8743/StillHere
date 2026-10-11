# MVP backend integration review

Integration owner: this chat. Started October 11, 2026. Shared checkout changes
present at start are preserved. Domain packages and `contracts/parallel/` are
agent proposals until their handoff and this review are complete.

Baseline: 330 discovered checks; 325 non-HTTP checks pass. Five real HTTP checks
fail because this host denies loopback binding, including an unrestricted retry.
No private configuration or credential files were opened or loaded.

## Assembly decisions

- CaseService owns snapshots, private check-in state, operator scopes, derived
  results, event replay and audit in one SQLite transaction.
- Operator credentials are provisioned through local database administration,
  never household HTTP/session payloads. Operator reads return consented review
  projections, never household snapshots/finance/chat. Assignment is authenticated.
- Check-in proposal state is stored privately. Its household projection retains
  shared `schedule`, `last_report` and `attempts`, plus typed occurrence history.
  Worker transitions use stable effect identities and run independently of models.
- Model-selected consent booleans cannot attest an explicit control. Enrollment
  and location sharing are direct authenticated controls; household tools can read
  status, reply, pause, clear sharing and request help without widening permissions.
- Planner cost exports and finance alternative records require a reviewed adapter.
  Null cost/date stays unknown; no unknown cost becomes zero, no completed spending
  or essential commitment is removed. Scenarios remain hypothetical.
- Application drafts are recomputed from authorized case and published rules in
  the commit transaction. Reported approval never creates received money.
- Output proposals are revalidated against current records inside CaseService.
  Structured questions cannot execute commands or grant authority.

## Review ledger

| Module | Proposal review | Shared assembly | Full MVP readiness | Live verification |
| --- | --- | --- | --- | --- |
| Planner | Existing bounded slices reviewed; extended proposal pending handoff | Existing saved plans/tasks retained | Pending extensions/cost review | Prior user-run bounded plan proof retained |
| Finance | Existing forecast reviewed; updates/scenarios pending handoff | Pending | Pending | Deterministic; no provider claim |
| Applications | Proposal arriving; pending handoff | Pending | Pending | No external submission |
| Check-ins/operator | Proposal arriving; projection/authority reconciliation required | Pending | Pending | Simulation only |
| Outputs | Proposal arriving; pending handoff | Pending | Pending | Scripted-provider proof pending |
| Deployment | Assets arriving; pending handoff | Pending | Pending acceptance/access | No deployment claim |

Synthetic F01–F07 helpers are in `tests/integration_fixtures.py`. Acceptance evidence,
counts and precise deployment gates will be recorded here after assembly.

## Deployment access follow-up

The user supplied `root@172.238.189.78` as the Akamai SSH target. A bounded,
noninteractive SSH check on October 11, 2026 failed before authentication with
`Operation not permitted`, both within the sandbox and after the approved-access
retry. No remote commands ran and no deployment changes were made. The user must
verify access from their terminal, or provide an execution environment that permits
SSH. Integrated acceptance, a TLS hostname/DNS configuration, and user-controlled
private provider configuration remain pending; the IP alone does not satisfy them.
