# Deployment preparation handoff

Prepared October 11, 2026. Ownership: **`deploy/`, deployment-specific checks, and
this file only**. Shared application/dependencies, README, progress documents and
private configuration were not edited. Concurrent application work is preserved.
No account resources were provisioned, no paid infrastructure was purchased and
no endpoint was published.

## Readiness and decisions

| Scope | State / evidence |
| --- | --- |
| Deployment-preparation assets | Prepared for integrator review; seven of eight initial deployment checks pass, one HTTP test blocked by host policy |
| Current application deployment | Not accepted or deployed; application/transport, target build and host access gates below remain |
| Full infrastructure / backend components | No readiness claim; this assignment does not advance C01/C02/worker component readiness |
| Bedrock live-provider proof | Prior application proof is recorded in agent docs; no new credentialed proof was run here |
| Akamai live verification | Pending integrated acceptance and account/SSH/DNS access |

Selected topology: one Akamai Compute Instance, Ubuntu 24.04 LTS x86_64, distribution
Python 3.12, native immutable release directory/venv, official Caddy systemd service,
private local SQLite/WAL on the instance disk, separate systemd API and future
worker, hourly SQLite online snapshots. Starting capacity assumption: 2 vCPU / 4
GiB, subject to budget/region/load acceptance. No LKE, NodeBalancer, separate volume
or managed database is needed for the preparation slice. All application runtime,
durable data and recovery copies remain on Akamai; Bedrock is inference only.

Native systemd avoids changing the current loopback binding for a container
network. The API remains `127.0.0.1:8000`; only Caddy exposes HTTP redirects/TLS.
Cloud Firewall rules must deny direct access to 8000/2019 in both address families.
SQLite stays outside immutable releases. The proxy forwards bearer/version headers
and request methods/bodies unchanged, with no retries/caching/authority mapping.
No filesystem browsing, private DB route, workshop `/chat`, operator-provisioning endpoint,
wildcard CORS or unauthenticated case lookup is added. The final scan found new
authenticated operator queue/case/command routes from concurrent integration;
Caddy forwards those explicit `/v1/operator/` paths without granting authority.

## Delivered files

- `deploy/build_release.py`: allowlisted source/catalog/schema packaging, exact
  wheel hashes/transitive versions, deterministic archive/manifest. An approved
  Linux wheelhouse is a required input; first dependency resolution is a separate
  acceptance step, then exact wheel bytes are reused.
- `deploy/verify_release.py`: extracted-release hash/layout verification before
  offline installation. Verify the externally trusted archive digest first.
- `deploy/Caddyfile`: hostname TLS, `/health` and `/v1` route boundary, 64-KiB
  body cap, bounded transport timeouts/32 backend connections, no access logging and discarded runtime
  request-error logs. Certificates persist in Caddy's private service state.
- `deploy/systemd/`: API/worker crash restart and boot policy; API credential mount;
  least-privilege state paths; fixed-label health and backup timer services;
  official Caddy service drop-in for non-secret configuration.
- `deploy/runtime.conf.example`: configuration names/default bounds/tool opt-ins,
  no credential values. Worker module intentionally blank.
- `deploy/run_worker.py`: separately runnable service launcher, rejects absent/
  invalid/local-server/smoke entry points, fixed private DB path. Worker is disabled
  until module acceptance plus a root-owned marker.
- `deploy/backup.py`: bounded, mode-0600, integrity/FK-checked online SQLite copy;
  restore refuses existing target directories and never overwrites a live DB.
- `deploy/healthcheck.py`: local health plus read-only SQLite checks, no provider
  call or household output. SQLite sidecar housekeeping needs state-dir access.
- `deploy/verify_http.py`: TLS-required remote synthetic-household proof with
  private mode-0600 state and fixed-label output; supports post-restart resume.
- `deploy/tests/test_deployment.py`: isolated synthetic deployment checks.
- `deploy/OPERATIONS.md`: build/freeze/install, identity/TLS provisioning, host
  firewall, restart/replay proof, backup/restore, retention, update/rollback and
  access/limitations instructions. All provisioning commands are operator-only
  after acceptance. No private file is needed for offline validation.

## Runtime entry points and integration contract

**API now:** `python -m backend.stillhere.server --db
/var/lib/stillhere/cases.sqlite3 --port 8000`, run from the release root. It loads
environment only from the process unless explicitly passed `--env-file`, which
these units never pass. `CaseHTTPServer` defaults to `AgentRuntime`; the latter
currently runs work inside the HTTP request and subsequent daemon threads.
The whole root `contracts/` directory and JSON resource/rule/source catalogs must
be shipped because imports use file-relative paths.

**Worker candidate arrived during preparation:** `backend.stillhere.worker`
implements a credential-free simulated check-in loop through
`CaseService.process_due_check_ins()`, with `--db`, `--interval` (default 15s),
`--once`, and SIGINT/SIGTERM shutdown. It emits no continuous logs and calls no
model/network provider. The worker service therefore loads no AWS credentials.
The module remains blank/disabled until the integrator accepts its final CLI,
authority, crash/idempotency, progress and simulation-only tests. The launcher expects an integrator-owned
`backend.stillhere.<accepted_module>` with `--db PATH`. It must remain in the
foreground, handle SIGTERM, stop claiming work while draining, use bounded polling
and clock/deadline semantics, and emit only approved redacted diagnostics. Its
boot recovery, progress/heartbeat and kill/restart behavior need synthetic proof.
It must dispatch through trusted application context and `CaseService`; never
read token digests as recoverable tokens, enumerate raw household rows as model
authority, fabricate operator/system sessions, bypass event/version/run claims,
write snapshots with SQL, or automatically replay failed effects. Current stored
session digests cannot reconstruct a household bearer token after process restart.
A future durable **agent** worker authority/claim API therefore belongs to
integration; this check-in worker does not reconstruct household sessions or drain
agent conversations. The launcher does not invent that API. Accepted case writes
remain CaseService-owned. The candidate bounds changed cases per poll but currently
scans all registered case IDs; load/fairness/progress require target acceptance.

Avoid adding a new agent worker which races current synchronous processing until
integration defines which process claims each kind of work and verifies mutual
exclusion. Define worker health separately from PID liveness; `/health` cannot
prove worker progress. The service stays disabled without
`/etc/stillhere/worker.accepted`, and the module name stays blank until acceptance.

## Exact proposed application patch for review (not applied)

The current server is a local stdlib adapter. Python's official
[HTTP server guidance](https://docs.python.org/3.12/library/http.server.html)
does not certify it for production. Caddy protects the public edge, but does not
make unbounded backend request threads or raw handler exceptions production-ready.
No application edit is needed to use this preparation slice for synthetic preview.
The following concrete, dependency-free patch is proposed to the application
owner to bound the existing adapter and suppress raw request tracebacks. It is
**not a substitute for accepting/replacing the production HTTP transport**.

```diff
--- a/backend/stillhere/server.py
+++ b/backend/stillhere/server.py
@@
 import json
+import threading
@@
     def __init__(self, address, service, agent_runtime=None):
         self.service = service
         self.agent_runtime = agent_runtime or AgentRuntime(service)
+        self.request_slots = threading.BoundedSemaphore(32)
         super().__init__(address, Handler)
+
+    def get_request(self):
+        request, address = super().get_request()
+        request.settimeout(15)
+        return request, address
+
+    def process_request(self, request, client_address):
+        if not self.request_slots.acquire(blocking=False):
+            self.shutdown_request(request)
+            return
+        try:
+            super().process_request(request, client_address)
+        except BaseException:
+            self.request_slots.release()
+            raise
+
+    def process_request_thread(self, request, client_address):
+        try:
+            super().process_request_thread(request, client_address)
+        finally:
+            self.request_slots.release()
+
+    def handle_error(self, request, client_address):
+        # No traceback, request path, case identity, body or token in logs.
+        pass
```

Integrator must test slot release on disconnect/failure, excess-client behavior,
socket deadlines, no raw tracebacks, SIGINT/SIGTERM and in-flight model work. The
32-slot proposal bounds request threads, but runtime daemon continuation threads
can still exceed that count; the future durable worker/production adapter must
bound total jobs and cost. Units already discard raw stdout/stderr and disable
core dumps, so no patch is assumed or silently applied. Do not increase process
limits to hide overload or automatically retry household commands at the proxy.

For a public production transport replacement, the application owner must supply
the final reviewed adapter/dependency diff and entry point before deployment; this
task has not invented one. It must preserve strict JSON/body validation, all
`CommandResult`/`AccessError` HTTP mappings, version headers, no-store responses,
household-versus-missing-case equivalence and existing command authorization.
After that diff is accepted, change only this slice's `ExecStart` and transport
tests to its final entry point. No contract version change is proposed.

## Configuration and secure provisioning

The API service credential chain uses root-owned `/etc/stillhere/aws-credentials`
(AWS shared `[default]` profile) through systemd `LoadCredential`; runtime points
`AWS_SHARED_CREDENTIALS_FILE` at `%d/aws-credentials`, disables metadata discovery
and clears environment credential overrides. The operator provisions/rotates
credentials on Akamai through a secure process; no local configuration is copied.
Temporary identity refresh requires service restart with this simple file chain;
a refreshable credential process can be accepted separately. AWS region and
model/profile selection are explicit. Model access/IAM conditions must match the
final inference calls; no Akamai token or AWS administrator identity is needed
by the application. Keep object-storage recovery identity separate from Bedrock.

Non-secret names: `AWS_REGION`, `STILLHERE_BEDROCK_MODEL_ID`, the seven
`STILLHERE_AGENT_` budget/history settings and all nine `ENABLE_` tool flags listed
in `runtime.conf.example`, plus `STILLHERE_WORKER_MODULE`.
Proxy names: `STILLHERE_DOMAIN`, `STILLHERE_ACME_EMAIL`.
Fixed state: `/var/lib/stillhere/cases.sqlite3`, `/var/backups/stillhere`,
`/var/lib/caddy`. Code: `/opt/stillhere/releases/<id>` and `current` symlink.
Do not put secret values in the templates, systemd environment, commands or logs.
Private developer `.env*`, AWS credential files and secret values were never read,
searched, printed, attached or copied during this task.

## Validation evidence and remaining checks

Initial execution and the final seven non-HTTP reruns after concurrent integration,
synthetic environment stripped with `env -i`, using local
Python 3.14.7 and installed SDK packages, temporary storage only:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest discover -s deploy/tests -v
```

- **Passed:** direct CaseService restart/session/isolation/replay; live WAL-reader
  consistent backup of a subsequent committed mutation and restored replay;
  refused existing restore target; missing/corrupt source cleanup; bounded backup;
  deterministic archive and altered-file detection; worker fail-closed/fixed DB;
  plaintext remote verifier rejection before network access.
- **Blocked:** real HTTP restart smoke cannot bind an ephemeral loopback socket
  (`PermissionError: Operation not permitted`), including the approved-access
  retry. This is an error, not a passing/skipped transport test. Normal test runs
  retain that requirement for target acceptance.
- **Blocked:** Linux-target wheel download from official PyPI fails DNS, including
  an approved-access retry. No resolved wheel lock, installed Linux release or
  real-SDK packaging compatibility is claimed. The deterministic packaging check
  uses explicitly fake wheel metadata only; those wheels are not installed.
- **Not available here:** Ubuntu systemd parser/runtime and Caddy binary. Run
  `systemd-analyze verify`, `caddy validate`, offline install/`pip check` and the
  complete deployment suite on the chosen target OS. Static preparation is not
  native configuration-validation evidence.

After source freeze and target build, the operator's acceptance includes:

1. Externally trusted release digest, identical rebuild digest, offline wheel/hash
   installation, timezone/seed/schema imports, exact runtime version record.
2. Native unit/Caddy validation; private ownership/modes; TLS issuance/renewal;
   firewall and loopback-only backend on both IP families; no public admin listener.
3. HTTPS synthetic household/access/replay proof, API restart, crash recovery,
   host reboot and immutable release cutover persistence with the same test state.
4. Verified WAL snapshot and offline restore into new state directory, scoped
   read/creation/command replay, measured recovery time, disk-loss recovery copy,
   approved retention/key escrow and alert destination.
5. Operator-run credentialed model proof against the deployed chain, followed by
   saved-state/replay verification; separate worker authority/crash/progress proof
   before enabling its service.

## Operating limits / unresolved access

The target host/account, region/plan, hostname, ACME email, SSH/sudo access, AWS
identity/model permissions, recovery bucket/host/key policy and operator alerting
are not available/selected by this assignment. Actual provisioning follows
integrated acceptance and available Akamai access.

This is a single-host MVP topology: no HA, failover, multi-host WAL, autoscaling,
zero-downtime upgrades or measured load/RTO. SQLite's five-second writer timeout
and total synchronous/continuation concurrency require target load proof. Anonymous
session creation has no deployed user/cost quota or recovery/expiry workflow yet;
general public use needs those integration decisions. No SMS/email, automatic
welfare outreach or real responder assignment is provisioned by a worker service.

Hourly snapshots protect process/release mistakes but local copies share host
failure risk. Encrypted Akamai recovery transfer, retention pruning and alert
delivery must be configured separately; until then snapshots accumulate. Restarts
can interrupt provider work/leave queued leases; no automatic reconciliation or
failed-effect replay is added. Raw application/proxy logs are suppressed for
privacy, limiting diagnostics to lifecycle/health/backup status until approved
redacted metrics are integrated. Do not equate these deployment assets with
public production acceptance or a new live-provider proof.

Official details were checked October 11, 2026: [Akamai Cloud Firewall](https://techdocs.akamai.com/cloud-computing/docs/getting-started-with-cloud-firewalls),
[Akamai backup limitations](https://techdocs.akamai.com/cloud-computing/docs/backup-service),
[Caddy automatic TLS](https://caddyserver.com/docs/automatic-https),
[Caddy proxy semantics](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[systemd credentials](https://github.com/systemd/systemd/blob/main/docs/CREDENTIALS.md),
[systemd restart behavior](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml),
[SQLite WAL](https://www.sqlite.org/wal.html) and
[pip repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
