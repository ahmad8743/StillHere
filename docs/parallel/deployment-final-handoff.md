# Final deployment asset handoff

Prepared October 11, 2026. Ownership: **`deploy/` and this file only**. Shared
CaseService, commands, contracts/schema, server, existing agent/tests, README,
shared progress and the earlier deployment handoff were not edited. All existing
uncommitted work is preserved. Handoffs/proposal schemas remain review boundaries.
No infrastructure, endpoint, certificate, credentials or paid recovery service was
provisioned. No SSH or live provider command ran in this task.

## Readiness ledger

| Scope | State | Evidence / required next step |
| --- | --- | --- |
| Deployment asset slice | PREPARED FOR REVIEW; target-dependent checks pending | 12 of 13 local deployment checks pass; the real HTTP test fails on host policy; scripts/patch syntax and application patch applicability checked |
| Proposed concurrency/durability slice | REVIEWABLE, unapplied | Exact owner patches apply cleanly; 27 agent tests pass in an isolated patched temporary copy, including the new timeout/capacity regression |
| Full integrated backend/release | PENDING integration-owner acceptance | Do not infer acceptance from this asset handoff or earlier proposal labels; final shared boundaries/transport and frozen source hashes require signoff |
| Linux target build/dependency compatibility | PENDING user-run | No real Linux wheel lock/offline install here; target-enforcing build and commands supplied |
| Target OS/architecture | UNCONFIRMED | User-run SSH OS/architecture/runtime probe required before relying on Ubuntu 24.04/x86_64/3.12 assets |
| Native unit/Caddy/ownership validation | PENDING user-run | Native Linux tools are absent here; no static/parser substitution claimed |
| Public IP TLS/renewal/deployed health | PENDING user-run | Trusted certificate issuance, dry-run/reload, external trust/SAN/expiry/health, natural renewed fingerprint and failure visibility evidence required |
| API/worker/reboot/SQLite/restore on target | PENDING user-run | Local independent worker and WAL/restore proofs are separate from actual service/host drills |
| Host-loss recovery, retention delivery | PENDING selection/access and rehearsal | Choose approved separate Akamai destination/key escrow/policy; perform recovery on a separate host and measure RPO/RTO |
| Deployed credentialed Bedrock | PENDING user-run | User provisions private server identity and runs accepted smoke; this task never reads developer credentials |
| Production readiness | NOT CLAIMED | Single host, stdlib transport, bounded-but-unmeasured load/cost/recovery/drain limitations |

The user supplied `root@172.238.189.78` and confirms SSH works from their Mac.
Workspace SSH previously failed `Operation not permitted` even after approved
retry. No remote command executed. No domain is available; domain/DNS is **no
longer** the TLS gate for this reviewed path. Target access from the user terminal,
IP control/reachability, OS confirmation, integration acceptance and private server
configuration still are gates.

## Final assets

The authoritative executable operator sequence is [deploy/OPERATIONS.md](../../deploy/OPERATIONS.md).
It includes separate Mac/target commands, expected assertions and failure handling.

- `preflight.py`: fail-closed Ubuntu 24.04/x86_64/CPython 3.12 checks; actual public
  OS/systemd/Caddy/Certbot version evidence. Other targets require review/adaptation.
- `build_linux.sh`, `build_release.py`, `verify_release.py`: exact approved
  wheel/transitive hashes, deterministic double build, trusted archive digest,
  allowlisted complete backend/catalog/contracts/shared/deployment tests, clean
  offline installation/`pip check`, full Linux-target acceptance suite. CLI build
  refuses the wrong platform. Packaging-only synthetic wheels are never installed.
  `lock_certbot.py` applies the same wheel/transitive hash verification to a
  separate pinned Certbot toolchain for offline installation and host recovery.
- `Caddyfile.bootstrap`, `Caddyfile`: literal accepted IPv4 address, ACME-only
  plaintext bootstrap, HTTPS-only API proxy, explicit manual trusted TLS pair,
  fixed-origin redirect and request/connection/time bounds. No fallback local CA,
  request logs, file browsing, CORS, caching, retries or authority translation.
- `tls_publish.py`, `tls_renew.py`, TLS renewal/health units/timers: hourly Certbot
  policy/ARI renewal check, root-only fixed-lineage publication, public trust/IP/
  expiry/key validation, fsynced atomic pair switch, Caddy-user validation, systemd
  reload, pointer rollback plus best-effort previous reload. Fixed-label errors;
  15-minute served TLS checks fail below 48h. Persisted hook plus wrapper retries
  publication after previous hook failure. Current/previous local pairs retained.
- `validate_native.sh`, `verify_permissions.py`: real systemd/Caddy validation
  and ownership/mode checks. App state is 0700/0600; root-owned code/venv;
  Caddy's TLS group never shares app state/credentials. No credential contents read.
- API/worker units: loopback-only API; independently registered simulation-only
  worker, disabled until acceptance marker/module selection; no IP networking or
  credential mount for worker. CaseService remains the sole domain writer.
- `verify_tls.py`, `verify_http.py`: normal client public CA/IP SAN/short lifetime/
  health and persistent two-household isolation, forbidden writes, command/creation
  replay and saved fact/version across API crashes/restarts/reboot. Redirects cannot
  downgrade TLS or forward synthetic bearers to another origin. Fixed-label output;
  mode-0600 state is disposable and never attached.
- `verify_worker.py`: new opt-in disposable deadline probe; actual version/effect
  progress, two poll intervals of stability, stable reminder/review IDs/content and
  original enrollment replay; repeat after worker crash/reboot and arm fresh overdue
  work for progress proof. No model/provider or live outreach call.
- `backup.py`, `verify_restore.py`: bounded integrity/FK-checked SQLite online
  snapshot, fsync/publication, restore refuses existing destinations, authorized
  CaseService scoped reads/replays against a separate restored database.
- `backup_status.py`, status timer: age/capacity failures after two missed hourly
  backups or below 20% free storage. `retention.py`: dry-run default, 48h/newest
  protection, removal only for exact hashes listed in a recent trusted off-host
  restore receipt. Unverified data is not deleted. Recovery tool commands and
  host-loss bundle/drill are prepared, with actual paid destination/access pending.
- `deploy/proposals/`: exact shared server/runtime/FULL-sync/test/documentation
  patches, review notes and acceptance limitations. No proposed schema/command
  changes. Owner may accept/revise; none are silently applied or assumed installed.

## Official documentation verified

Checked October 11, 2026 through official sources:

- [Let’s Encrypt IP/six-day availability](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
  and [Certbot IP webroot guidance](https://letsencrypt.org/2026/03/11/shorter-certs-certbot):
  IP certificates are short-lived, 160h; Certbot 5.4+ webroot supports this flow.
  Staging is intentionally untrusted and does not satisfy acceptance.
- [Certbot renewal/hooks](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates),
  [isolated installation](https://certbot.eff.org/instructions?ws=other&os=pip),
  [Caddy packaged service](https://caddyserver.com/docs/running#linux-service),
  [Caddy install](https://caddyserver.com/docs/install#debian-ubuntu-raspbian),
  and [manual TLS directive](https://caddyserver.com/docs/caddyfile/directives/tls).
  Chosen reviewed Certbot pin 5.8.0 matches current official documentation; review
  dependency lock/security upgrades instead of assuming Ubuntu's old package supports IPs.
- [OpenSSL public chain/IP verification](https://docs.openssl.org/3.0/man1/openssl-verification-options/),
  [pip repeatable installs](https://pip.pypa.io/en/stable/topics/repeatable-installs/),
  [systemd credentials](https://github.com/systemd/systemd/blob/main/docs/CREDENTIALS.md),
  [SQLite online backup](https://www.sqlite.org/backup.html) and
  [restic retention](https://restic.readthedocs.io/en/stable/060_forget.html).

These sources justify asset choices; they are not evidence of this host's installation.

## Actual verification evidence

Local runtime: macOS / installed CPython 3.14.7, empty process environment,
ResourceWarnings treated as errors, temporary synthetic databases/configuration only.
No private `.env*`, AWS credential file, values or developer identity was accessed.

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m unittest discover -s deploy/tests -v
```

Final discovery: **13 checks; 12 pass; one real HTTP bind error**. The approved
unrestricted retry also fails with `PermissionError: Operation not permitted`.
The error is not skipped or counted as a pass. Passed behavior includes:

- Direct CaseService persisted session/case isolation and replay after reopen.
- Committed WAL data preserved by online snapshot and separate restore; invalid
  source/existing target refusal and bounded copy cleanup.
- Deterministic archive/hash tamper detection and exclusion of private/config/data/
  frontend paths, using fake metadata explicitly labeled packaging-only evidence.
- Independent concurrent `backend.stillhere.worker --once` processes: exactly one
  changed case/effect set; another process restart gives identical saved effects.
  This is local simulation evidence, not systemd/host worker-operation evidence.
- TLS publication rollback under a simulated reload failure; no production cert
  or native Caddy execution in that test.
- Recent verified-recovery receipt/hash/newest protection for retention; stale
  snapshot status failure; remote plaintext/redirect refusal.
- Two-household proof against direct CaseService test adapter and that same saved
  state checked against a separate restored DB. This is not a transport test pass.

All Python assets compile; Bash scripts pass `bash -n`. Five exact patches pass
`git apply --check`. The server/runtime/FULL-sync/test/docs proposals were applied
**only to an isolated temporary copy**, where all **27 `tests.test_agent` checks**
passed, including blocked-provider timeout/capacity regression. Shared files were
not edited. This staged result is not integrated-owner acceptance. Server socket
saturation/disconnect/deadline/drain tests still require a transport-capable host.

No Linux wheelhouse, offline Linux install, native systemd/Caddy parser, installed
service, certificate issuance/renewal, remote firewall, deployed health, reboot,
remote restore, paid recovery service, host-loss RPO/RTO or deployed Bedrock was
verified. The user-run commands and assertions are provided; states remain pending
until actual evidence arrives.

## Integration proposals and residual limits

`server-concurrency.patch` bounds request threads/sockets and suppresses raw handler
tracebacks. `runtime-concurrency.patch` bounds actual provider work including calls
still running after HTTP timeout, and caps continuation threads. Accepted work can
remain queued at capacity and needs later authorized replay; a durable agent worker
with authority/claims/drain would require a separate owner contract. Four provider
slots is a proposed budget choice, not measured host capacity. `sqlite-durability.patch`
requests explicit FULL sync per connection, preserving existing transactional authority.
`shared-tests.patch` supplies the timeout regression; `shared-docs.patch` corrects
the obsolete domain gate and points shared readiness to this ledger without claiming
component completion. No commands/contracts/schema edits are needed for this path.

Worker current implementation scans all case IDs and takes a transaction per case;
changed-case batching does not bound scan time. Acceptance must measure scan fairness,
SQLite busy contention with API, SIGTERM stop time and restart progress on target.
No application fix is silently placed in deployment code. Root/user-owned acceptance
marker is an operator gate, not proof that integration tests passed. Reassess marker
and module on release changes. No durable agent-turn recovery or automatic replay
of failed effects is introduced.

## User-run gates and acceptance record

Record these independently, in order; do not promote pending items by assumption:

1. OS/architecture/versions, host-key/firewall/console and operator access; integrated
   source/signoff and reviewed shared patches/schemas/transport.
2. Approved wheelhouse, repeatable trusted archive digest, offline Linux install,
   shared/deployment tests, actual native unit/Caddy/permissions/listener validation.
3. User-controlled private server identity/model configuration, bounded accepted
   credentialed smoke with safe evidence; no developer credentials copied.
4. Trusted IP SAN certificate, external TLS health, dry-run/reload failure recovery,
   hourly renewal status, natural renewed certificate fingerprint and notification
   visibility/delivery through the selected external monitor.
5. SAME two-household proof across API restart/crash/host reboot; consistent snapshot,
   separate restore/replay; accepted independent worker fresh-deadline progress and
   SAME-effect stability across worker crash/restart/reboot.
6. User-selected recovery destination/key escrow/retention; recovered trusted snapshot
   on a separate approved Akamai host, compatible release/key/identity/network rebuild,
   measured RPO/RTO and public TLS/worker/household proofs. No new paid storage without
   authorization. External alert recipient/channel is still unselected.

Provide only public certificate metadata, release hashes, fixed labels/counts,
unit Results and measured durations as evidence. Private proof states/credential
files/raw household or provider logs are never review artifacts. No live outreach,
production-readiness, installation, TLS, recovery or worker-operation claim is made.
