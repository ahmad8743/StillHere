# Exact application proposals — integration owner only

October 11, 2026. None of these patches is applied to the shared checkout.
They are incremental proposals against the currently uncommitted source, not an
assertion that those changes have already been accepted. Preserve that source.

```sh
git apply --check deploy/proposals/server-concurrency.patch \
  deploy/proposals/runtime-concurrency.patch deploy/proposals/sqlite-durability.patch \
  deploy/proposals/shared-docs.patch deploy/proposals/shared-tests.patch
```

- `server-concurrency.patch`: cap request threads at 32; accepted socket timeout
  15s; release permits on failures; suppress raw request exception tracebacks.
  Excess connections close without automatic retry. Caddy still caps connections.
  Integration must test saturation/disconnect/error permit release, slow bodies,
  SIGINT/drain and HTTP result mappings. Python's stdlib transport is still not
  production-certified. This patch does not replace it.
- `runtime-concurrency.patch`: cap actual provider calls at four, INCLUDING
  calls which exceed response timeout but have not exited. Bound continuation
  threads at four. Leave durable accepted work queued when slots are full; do not
  fabricate a failure or replay financial effects. All claims/writes stay in
  CaseService. Queued work needs a later authorized replay to progress if no
  continuation slot is available; this remains an integration UX/recovery gate.
  No agent worker authority is invented. Shutdown/drain is not solved by this
  patch. API and provider counters are per singleton runtime in the single API
  process; multiple replicas are not supported. Four calls is a reviewed MVP
  candidate, not a measured cost/load limit.
- `sqlite-durability.patch`: explicitly set FULL synchronous per connection
  for WAL commit power-loss semantics. SQLite's default is often FULL, but explicit
  configuration avoids silently inheriting a weaker choice. Target filesystem,
  actual PRAGMA and reboot/restore evidence still matter. No schema change.
- `shared-tests.patch`: exact regression addition to owner-controlled agent tests
  for provider calls that outlive timeout; staged review test uses synthetic cases
  and a blocking fake provider only. Existing shared tests remain untouched.
- `shared-docs.patch`: proposed README deployment pointer, backend integration
  IP-certificate/access correction and C16 readiness boundary update. No accepted
  component or live-verification status is upgraded.

No change is proposed to commands, contracts.py, shared schemas or existing tool
registry. Do not enable proposed domain schemas/tools from handoffs without the
integration owner's boundary review. The separate check-in candidate already uses
CaseService BEGIN IMMEDIATE per transition and stable unique effect identities;
no extra lock is silently added. Its all-case scan and no-op write-lock behavior
need scale/host acceptance. A future bounded scan/progress metric API belongs to
CaseService and requires an owner-designed cursor/clock/transaction contract.

Deployment tests additionally verify independent concurrent worker processes and
stable subsequent effect sets, restored replay/isolation and TLS reload rollback.
These local tests do not prove deployed network, systemd, power loss or host loss.
