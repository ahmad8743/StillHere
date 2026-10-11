# StillHere agent development

Build agent/tool capabilities incrementally from docs/contracts-and-progress.md and
docs/strands-capabilities.md. Record slice readiness separately from full-component
readiness and live-provider verification. CaseService owns all durable writes.

## Secrets

Never open, search, print, attach, or summarize .env, .env.local, other .env.* files,
AWS credential files, or secret values. The tracked blank .env.example is safe to read.
Use synthetic configuration in tests. Do not load the user's .env.local when running
tests or diagnostics. The user runs the live service and credential smoke test.
Do not ask the user to paste credentials into chat. Direct them to .env.local or the
external AWS credential chain. Git ignore patterns do not enforce Codex read denial;
see docs/agent-integration.md for the permission-profile configuration.
