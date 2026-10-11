# StillHere backend deployment and verification

Prepared October 11, 2026. Owner: `deploy/` and the final deployment handoff only.
All commands below are **user-run**. Deployment starts only after the integration
owner accepts the frozen backend, executable shared boundaries and transport.
Nothing here certifies production readiness. CaseService owns every application
write. Check-ins and reviews remain simulations; no outreach, Plaid or frontend.

## Evidence and remaining gates

| Scope | Status |
| --- | --- |
| Deployment assets | Reviewable; local synthetic evidence in final handoff |
| Integrated acceptance | Pending owner signoff for the final source/release hash; stale proposal handoffs are not signoff |
| Target OS/architecture | Unconfirmed; commands refuse anything except Ubuntu 24.04 / x86_64 / CPython 3.12 |
| Linux wheel lock/install | User-run pending; packaging tests use fake metadata, not installed SDK evidence |
| Native systemd/Caddy/ownership | User-run pending |
| Trusted deployed IP TLS / renewal | User-run pending |
| Restart/reboot/restore/worker | User-run pending; local worker-process checks are separate |
| Credentialed deployed Bedrock | User-run pending; no credentials accessed here |
| Host-loss recovery / alert delivery | Selection/access and measured rehearsal pending |

Target: `root@172.238.189.78`. The user confirms SSH works from their Mac. This
workspace's SSH failed with `Operation not permitted` even after an approved retry;
no remote command ran. Do not assume an accessible remote executor here.

No domain is required. Let’s Encrypt now issues IP certificates valid for 160
hours. Its [official Certbot guide](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)
requires Certbot **5.4+** for IP webroot validation. Production issuance, normal
client trust, automated renewal, reload and observed serial/fingerprint change
must all pass. Staging certificates, `tls internal`, `curl -k` and plaintext
health checks do not count as deployed TLS acceptance.

Still-required user choices: ACME email/terms acceptance; administrative sudo and
console recovery access; firewall source ranges; provider region/model/identity
and refresh procedure; approved build input versions; recovery destination on a
separate Akamai host or private Akamai Object Storage, retention/key escrow,
RPO/RTO; and an alert recipient/channel. No additional paid service is provisioned
or authorized by this runbook. Existing host sizing/region/plan still needs load
acceptance. Local backups do not provide host-loss recovery. Alert timers supply
local visibility; they do not deliver notifications until a recipient is selected.

## 1. Confirm target before using Linux assets

From the user's Mac, verify the host key through a trusted Akamai console first:

```sh
ssh root@172.238.189.78 'uname -srm; cat /etc/os-release; python3 --version; systemd-analyze --version'
```

These read only public OS/runtime information. Record OS ID/version, CPU architecture
and Python version. If different from Ubuntu 24.04 / x86_64, STOP and adapt the
package, units and build target before installing. An arm64 wheelhouse is not
interchangeable. After confirmed OS and accepted integration, install distribution
Python 3.12, venv, tzdata, CA roots, OpenSSL and Caddy following
[official Caddy installation](https://caddyserver.com/docs/install#debian-ubuntu-raspbian).
Use its packaged native systemd service; record exact installed versions and package
origins. Certbot is isolated from the application venv:

```sh
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv tzdata ca-certificates openssl
```

5.8.0 is the official documentation version checked for this runbook, not a claim
that it will always be latest. Resolve once on the isolated confirmed Linux
builder and review/freeze its separate transitive wheelhouse, then install offline:

```sh
# Builder with synthetic environment and no credential directories:
python3.12 -m venv /tmp/stillhere-certbot-builder
mkdir -m 700 /tmp/stillhere-certbot-wheels
/tmp/stillhere-certbot-builder/bin/python -m pip --isolated download \
  --index-url https://pypi.org/simple --only-binary=:all: --no-cache-dir \
  'certbot==5.8.0' --dest /tmp/stillhere-certbot-wheels
python3.12 -B deploy/lock_certbot.py --wheelhouse /tmp/stillhere-certbot-wheels \
  --output /tmp/stillhere-certbot.lock
# Transfer only these approved artifacts/digests to corresponding target paths.
sudo python3.12 -m venv /opt/certbot
sudo /opt/certbot/bin/python -m pip --isolated install --no-index \
  --find-links /tmp/stillhere-certbot-wheels --only-binary=:all: --require-hashes \
  -r /tmp/stillhere-certbot.lock
sudo /opt/certbot/bin/python -m pip check
/opt/certbot/bin/certbot --version
```

Retain exact wheels, trusted lock/digests and version/origin evidence off-host.
Review upgrades
before changing the pin. Installation is based on the
[official isolated pip instructions](https://certbot.eff.org/instructions?ws=other&os=pip).
Do not run distribution/snap renewal timers alongside the custom one below.

Upload only allowlisted code/releases; never upload the developer checkout wholesale,
private configuration, AWS files or a developer venv. Once assets are staged:

```sh
python3.12 -B deploy/preflight.py
```

Expected: non-secret JSON with Ubuntu 24.04, x86_64, CPython 3.12, actual systemd,
Caddy and Certbot versions. A failure is a gate, not a reason to bypass the check.
Builder validation uses `--builder` and does not require systemd/Caddy/Certbot.

## 2. Frozen Linux release and dependencies

Use a disposable confirmed Linux builder with no private configuration or AWS
credential directories. Integration owner reviews the current proposals and accepts
the exact source before freezing. Preserve the working checkout; never clean/reset
it to manufacture an accepted commit. Use a separate accepted clean checkout/export.
Record accepted revision, source hashes, OS image, Python patch, pip version,
Caddy and Certbot version/lock; the release manifest's target is a declared build
requirement, not evidence that the server has that OS.

First resolution is a separate review step. Rebuilds reuse **identical approved
wheel bytes**, rather than rerunning transitive resolution:

```sh
python3.12 -B deploy/preflight.py --builder
python3.12 -m venv /tmp/stillhere-builder
mkdir -m 700 /tmp/stillhere-wheels
/tmp/stillhere-builder/bin/python -m pip --isolated download \
  --index-url https://pypi.org/simple --only-binary=:all: --no-cache-dir \
  -r backend/requirements-agent.txt --dest /tmp/stillhere-wheels
bash deploy/build_linux.sh ACCEPTED_REVISION /tmp/stillhere-wheels /tmp/stillhere-build-UNIQUE
```

Replace `ACCEPTED_REVISION` with the integration owner's actual accepted revision.
The script enforces target compatibility, builds twice and compares bytes, verifies
extracted hashes, installs exact transitive hashes offline, runs `pip check`, and
runs **all shared acceptance tests plus deployment tests** with an empty synthetic
environment. An HTTP bind error is a failed build gate. No test loads a private
configuration. Timezone data and all JSON catalogs/contracts must be present.
[Repeatable pip installation](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
provides the dependency basis. This is not a reproducible OS image.

Builder reads only Python/JSON under backend/contracts/tests and allowlisted deploy
assets. It excludes hidden/config/data/frontend paths and links. `requirements.lock`
records every distribution/version/wheel SHA-256. `release.json` hashes every file.
Keep the expected **archive** SHA-256 in a separate trusted approval channel; an
embedded manifest alone cannot authenticate a release. Retain the archive and exact
wheelhouse off-host with the recovery bundle.

Linux wheels are not present/verified in this workspace. No dependency download,
Linux installation or SDK packaging compatibility is claimed. Failed package DNS
from the earlier handoff is not passing evidence.

On the confirmed target, transfer only the accepted archive and trusted digest from
the Mac, and extract as a non-root staging user before copying into a root-owned
immutable release. Do not extract arbitrary archives as root.

```sh
scp /PATH/TO/ACCEPTED/release.tar.gz root@172.238.189.78:/tmp/stillhere-release.tar.gz
```

Check the archive against the separately accepted digest BEFORE extraction:

```sh
printf '%s  %s\n' ACCEPTED_SHA256 /tmp/stillhere-release.tar.gz | sha256sum -c -
mkdir -m 700 /tmp/stillhere-release-stage-UNIQUE
tar -xzf /tmp/stillhere-release.tar.gz -C /tmp/stillhere-release-stage-UNIQUE
python3.12 -B /tmp/stillhere-release-stage-UNIQUE/deploy/verify_release.py /tmp/stillhere-release-stage-UNIQUE
```

Run extraction/verifier as the unprivileged staging user; return to sudo for install.
If the root SCP upload is mode 0600, grant that approved staging account ownership
first with `sudo chown APPROVED_STAGING_USER:APPROVED_STAGING_GROUP /tmp/stillhere-release.tar.gz`
and `sudo chmod 0600 /tmp/stillhere-release.tar.gz`; substitute its actual account/group.
Verification must precede creating a venv/bytecode. It rejects unexpected files and
changed bytes. Archive verification is not target acceptance or dependency proof.

## 3. Private host layout and immutable install

Single Akamai host; API binds `127.0.0.1:8000`; Caddy alone exposes :443. SQLite/WAL
is local disk `/var/lib/stillhere/cases.sqlite3`. Caddy admin remains loopback :2019.
Cloud/host firewalls drop inbound except TCP 80/443 and TCP 22 from approved
operator source ranges; enforce both IPv4/IPv6. API/admin must not be public. Keep
console recovery access; establish a sudo SSH-key account before disabling root
or password login. Do not lock out the only operator. See
[Akamai Cloud Firewall guidance](https://techdocs.akamai.com/cloud-computing/docs/getting-started-with-cloud-firewalls).
Allow required DNS, HTTPS and clock synchronization outbound. Do not guess fixed
Bedrock/public-source endpoint addresses. Confirm accurate time for IAM/ACME/deadlines.

After integration acceptance, run as operator on the target:

```sh
sudo useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin stillhere
sudo install -d -o root -g root -m 0755 /opt/stillhere/releases /etc/stillhere
sudo install -d -o stillhere -g stillhere -m 0700 /var/lib/stillhere /var/backups/stillhere
sudo install -d -o root -g caddy -m 0755 /var/lib/stillhere-acme
sudo install -d -o root -g caddy -m 0750 /etc/stillhere/tls
sudo cp -R /tmp/stillhere-release-stage-UNIQUE /opt/stillhere/releases/RELEASE_ID
sudo chown -R root:root /opt/stillhere/releases/RELEASE_ID
sudo chmod -R go+rX /opt/stillhere/releases/RELEASE_ID
sudo python3.12 -m venv /opt/stillhere/releases/RELEASE_ID/.venv
sudo /opt/stillhere/releases/RELEASE_ID/.venv/bin/python -m pip --isolated install \
  --no-index --find-links /opt/stillhere/releases/RELEASE_ID/wheelhouse \
  --only-binary=:all: --require-hashes -r /opt/stillhere/releases/RELEASE_ID/requirements.lock
sudo /opt/stillhere/releases/RELEASE_ID/.venv/bin/python -m pip check
sudo ln -s /opt/stillhere/releases/RELEASE_ID /opt/stillhere/current
```

Use a NEW release ID; `cp` is allowed only after confirming that destination does
not exist. The initial link fails if `current` already exists; use cutover below.
Create the venv at its final path; venvs cannot be relocated. No service can modify
root-owned code. All data directories are 0700, database/sidecars/snapshots 0600.
`/etc/stillhere` is traversable so Caddy can access its separate TLS subdirectory;
private config files retain file-level permissions. Caddy is not in the application
group and cannot access database or application credentials.

From now on run asset commands from `/opt/stillhere/current`. Register services
independently, leaving the worker disabled:

```sh
cd /opt/stillhere/current
sudo install -o root -g stillhere -m 0640 deploy/runtime.conf.example /etc/stillhere/runtime.conf
sudoedit /etc/stillhere/runtime.conf
sudo install -o root -g root -m 0644 deploy/systemd/stillhere-*.service deploy/systemd/stillhere-*.timer /etc/systemd/system/
sudo install -d -o root -g root -m 0755 /etc/systemd/system/caddy.service.d
sudo install -o root -g root -m 0644 deploy/systemd/caddy.service.d.conf /etc/systemd/system/caddy.service.d/stillhere.conf
sudo systemd-analyze verify /etc/systemd/system/stillhere-*.service /etc/systemd/system/stillhere-*.timer
sudo systemctl daemon-reload
```

`runtime.conf` has non-secret region/model selection, budget limits and tool opt-ins.
Enable only reviewed capabilities; keep worker module blank until section 6. Units
never pass `--env-file`. API uses systemd `LoadCredential` with the SDK shared-file
chain mounted at `%d/aws-credentials`; metadata discovery and environment overrides
are disabled. The **user** provisions root-owned mode-0600
`/etc/stillhere/aws-credentials` using a secure editor/provisioner on the server,
independently of developer credentials. Never inspect/print that file here or copy
private developer files. Scope Bedrock IAM to the selected model/profile destinations
and invocation methods. Akamai application runtime, data and backups stay on Akamai;
Bedrock is inference only. Do not enable storage of household invocation prompts
in AWS for this topology. Application credentials are separate from recovery credentials.

A simple temporary shared-file identity needs secure replacement and API restart
before expiry. Select a refreshable external chain if appropriate; the integration
owner reviews adapter changes. See
[systemd credentials](https://github.com/systemd/systemd/blob/main/docs/CREDENTIALS.md)
and [AWS shared-file configuration](https://docs.aws.amazon.com/sdkref/latest/guide/file-format.html).
The simulation worker has no credential mount, uses `/dev/null` SDK files and
allows only AF_UNIX, denying IP networking.

## 4. Public IP TLS bootstrap, renewal and failure visibility

Only after integrated acceptance and firewall/access checks, install bootstrap
Caddy configuration. It serves only ACME challenge tokens; all other requests get
503 and no API route. No private key exists in the repository.

```sh
cd /opt/stillhere/current
sudo install -o root -g caddy -m 0640 deploy/Caddyfile.bootstrap /etc/caddy/Caddyfile
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable --now caddy
```

Choose the ACME email and accept the subscriber terms deliberately. Test issuance
first in completely separate staging paths. Staging output must never be published:

```sh
sudo /opt/certbot/bin/certbot certonly --staging --non-interactive --agree-tos \
  --email APPROVED_ACME_EMAIL --required-profile shortlived \
  --webroot --webroot-path /var/lib/stillhere-acme --ip-address 172.238.189.78 \
  --cert-name stillhere-ip-stage --config-dir /etc/letsencrypt-stage \
  --work-dir /var/lib/letsencrypt-stage --logs-dir /var/log/letsencrypt-stage
sudo /opt/certbot/bin/certbot certonly --non-interactive --agree-tos \
  --email APPROVED_ACME_EMAIL --required-profile shortlived \
  --webroot --webroot-path /var/lib/stillhere-acme --ip-address 172.238.189.78 \
  --cert-name stillhere-ip
sudo chmod 0700 /etc/letsencrypt /var/lib/letsencrypt /var/log/letsencrypt \
  /etc/letsencrypt-stage /var/lib/letsencrypt-stage /var/log/letsencrypt-stage
sudo /usr/bin/python3 deploy/tls_publish.py --initial
sudo install -o root -g caddy -m 0640 deploy/Caddyfile /etc/caddy/Caddyfile
sudo -u caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
sudo /opt/certbot/bin/certbot reconfigure --cert-name stillhere-ip \
  --deploy-hook '/usr/bin/python3 /opt/stillhere/current/deploy/tls_publish.py'
sudo /opt/certbot/bin/certbot renew --cert-name stillhere-ip --dry-run --run-deploy-hooks
```

Keep `/etc/letsencrypt`, its work/log directories and staging counterparts private
root-owned; never grant Caddy access to the ACME account key or entire lineage tree.
The server hook alone copies the fixed approved lineage into root:caddy 0750/0640
TLS pair directories, validates IP SAN, expiry (>48h), public chain trust and
key match with OpenSSL, fsyncs, atomically switches one symlink for **both files**,
then validates Caddy as its service user and reloads via native systemd. Failures
restore the previous pointer and attempt to reload it; persistent rollback failure
is a failed operation requiring operator action, never reported as success.
It retains current/previous published pairs, and Certbot keeps lineage history.
Certbot `--dry-run --run-deploy-hooks` uses the current real certificate in hooks,
[as documented](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).
The public trust check rejects staging/self-signed chains. Runtime request logs are
discarded; root-private Certbot diagnostics are not chat artifacts. Hook/wrapper
output consists only of fixed labels.

Hourly renewal checks use Certbot's stored renewal policy/ARI, without force-renewing
hourly. The wrapper also reconciles/retries certificate publication if a prior hook
failed after issuance. Certificates are loaded manually into Caddy; Caddy does not
issue a fallback local-CA certificate. Bootstrap/renewal use HTTP-01 on port 80;
this public ACME path is not a plaintext application service.

```sh
sudo systemctl enable --now stillhere-tls-renew.timer stillhere-tls-health.timer
sudo systemctl start stillhere-tls-renew.service
sudo systemctl list-timers --all 'stillhere-*'
sudo systemctl show stillhere-tls-renew.service -p Result -p ExecMainStatus
sudo systemctl show stillhere-tls-health.service -p Result -p ExecMainStatus
```

TLS-health timer checks actual served trust/SAN/health every 15 minutes and fails
below 48h remaining. Renewal timer's failed unit/status and fixed label provide
failure visibility without request logs. Configure the selected external/on-call
monitor to alert on failed unit, no renewal check within two hours, or the external
TLS-health failure. Observe an actual automatically renewed certificate fingerprint
change before accepting renewal. Save public metadata before/after with section 5;
do not force-renew repeatedly. A stopped host cannot alert itself: an external
monitor and approved destination/access remain gates. No outbound message is sent
or notification integration provisioned here.

Failure drill: during a synthetic maintenance window, temporarily stop
`stillhere-tls-renew.timer`, run `sudo systemctl edit --runtime stillhere-tls-renew.service`
with `[Service]`, empty `ExecStart=`, then `ExecStart=/usr/bin/false`; start it and
assert failed Result/nonzero status is observed by the selected monitor. Remove
only that runtime drop-in, daemon-reload, reset-failed, run the genuine service,
and restart the timer. Do not disable actual renewals for a six-day certificate
without a bounded maintenance window and immediate recovery. Test expiry alerts
through the selected monitor's test facility, not by serving an expired/untrusted
certificate to users. Monitor delivery remains pending until received evidence.

## 5. Native acceptance, TLS, isolation, restarts and reboot

On target after private credentials are user-provisioned:

```sh
sudo bash /opt/stillhere/current/deploy/validate_native.sh
sudo systemctl enable --now stillhere-api.service
sudo systemctl start stillhere-health.service stillhere-backup.service
sudo systemctl enable --now stillhere-health.timer stillhere-backup.timer stillhere-backup-status.timer
sudo systemctl start stillhere-backup-status.service stillhere-tls-health.service
sudo ss -ltnp
sudo systemctl is-active stillhere-api.service caddy.service
```

Expected `native_validation_ok`, `ownership_verified`, successful health/backup/TLS
unit results; backend listener **only** 127.0.0.1:8000 and admin only loopback:2019.
From an external authorized Mac, connection attempts to 8000/2019 must fail on each
assigned IP family. The IP certificate covers only 172.238.189.78; no IPv6 TLS
identity is claimed. Inspect firewall policy separately; an untested address family
is not accepted. Caddy/proxy body cap is 64 KiB; no caching/retries or authority
translation. `GET /health` cannot prove Bedrock, worker progress or writes.

On the Mac, use private disposable state (contains **synthetic** bearer tokens):

```sh
umask 077
mkdir -m 700 /tmp/stillhere-proof-UNIQUE
python3 deploy/verify_tls.py > /tmp/stillhere-proof-UNIQUE/tls-before.json
curl --fail --silent --show-error https://172.238.189.78/health
curl --silent --show-error --output /dev/null --write-out '%{http_code} %{redirect_url}\n' http://172.238.189.78/health
python3 deploy/verify_http.py --base https://172.238.189.78 --state /tmp/stillhere-proof-UNIQUE/households.json
```

Expected trusted `tls_health_ok` in metadata, health 200, HTTP 308 to HTTPS;
`deployed_verification_ok` checks two durable household cases/sessions, symmetric
foreign access rejection, foreign mutation rejection, missing-case equivalence,
no-bearer/operator denial, unchanged original fact/version, creation and command
replay with original applied version. Reuse the SAME state for subsequent drills.
Unknown Host/route must never return household/API data. Certificate validation
uses default OS roots and explicit IP SAN; there is no insecure bypass.

Restart/crash commands are target-only, during a disposable acceptance window:

```sh
sudo systemctl restart stillhere-api.service
sudo systemctl start stillhere-health.service
sudo systemctl kill --kill-whom=main --signal=SIGKILL stillhere-api.service
sleep 8
sudo systemctl is-active stillhere-api.service
```

After EACH restart/crash, from Mac:

```sh
python3 deploy/verify_http.py --base https://172.238.189.78 --state /tmp/stillhere-proof-UNIQUE/households.json --resume
python3 deploy/verify_tls.py
```

Services restart failures after five seconds, with five starts per five minutes;
a deliberate clean stop remains stopped. Investigate a reached start limit, correct
its cause, then `reset-failed` before starting. Do not silently increase limits.
After worker acceptance/drills below, perform a deliberate host reboot:

```sh
sudo systemctl reboot
```

Wait for SSH from Mac, then assert API/Caddy/accepted worker active, all enabled
timers registered, ownership, listener and health checks pass. Repeat both public
verifiers plus SAME worker proof after reboot. Record actual reboot downtime; no
reboot, installation or durability claim is made before those outputs arrive.
After natural renewal, save `python3 deploy/verify_tls.py` as `tls-after.json` and
compare fingerprint/notAfter with before. Trust, healthy reload, timer success
and a changed public certificate are the renewal acceptance evidence.

## 6. Independent simulated worker and duplicate-free progress

The shared `backend.stillhere.worker` candidate is separately registered by
`stillhere-worker.service`, with crash restart/boot policy and a marker condition.
No API restart is needed to run it. It calls only CaseService; no fabricated
household/system session, raw case SQL writes, model call or live outreach exists
in this registration. The launcher only accepts that exact module. API `/health`
or a running PID does not prove deadline progress.

Integration owner must accept final command/schema projections, authority,
transactional effects and the worker's no-network behavior, plus current scan/load
limits. The candidate scans all case IDs and acquires a transaction per case; the
batch bounds **changes**, not total scanned cases. Host load/fairness/drain timing
remain unmeasured. Worker acceptance is tied to the frozen release, and must be
re-reviewed on each release. Model turns are a separate runtime path; this worker
does not recover unfinished agent conversations.

ONLY after integrated acceptance and worker tests pass, the user sets
`STILLHERE_WORKER_MODULE=backend.stillhere.worker` with `sudoedit` and records the
accepted release hash in a root-owned marker:

```sh
sudoedit /etc/stillhere/runtime.conf
sudo install -o root -g root -m 0600 /dev/null /etc/stillhere/worker.accepted
sudoedit /etc/stillhere/worker.accepted
sudo systemctl enable --now stillhere-worker.service
sudo systemctl is-active stillhere-worker.service
```

The marker records human acceptance; its existence alone is not verification.
Missing marker prevents startup. Missing/other module fails closed. The worker
has no IP network capability and no application credential mount.

On Mac, arm a new disposable case with explicit synthetic opt-in and a due time
60s ahead; while it is pending, independently restart the worker on target:

```sh
python3 deploy/verify_worker.py arm --base https://172.238.189.78 --state /tmp/stillhere-proof-UNIQUE/worker.json
```

```sh
sudo systemctl restart stillhere-worker.service
sudo systemctl is-active stillhere-api.service stillhere-worker.service
```

Then on Mac (bounded to 150s progress + 35s stability observation):

```sh
python3 deploy/verify_worker.py wait --base https://172.238.189.78 --state /tmp/stillhere-proof-UNIQUE/worker.json
```

Expected `worker_progress_replay_ok`: version advanced from enrollment, one
simulation:true reminder and one simulation:true unassigned review, no change
across two normal polling intervals, unchanged stable IDs/content after replay.
Kill/restart worker, rerun wait with the SAME state, and assert identical effects:

```sh
sudo systemctl kill --kill-whom=main --signal=SIGKILL stillhere-worker.service
sleep 8
sudo systemctl is-active stillhere-worker.service stillhere-api.service
```

Also arm a NEW probe before a worker stop or host reboot, restart afterward and
wait: persisted overdue work must catch up. Existing completed probe verifies no
duplicate, but alone does not prove future progress. Direct API writes continue
while worker is stopped. No direct `--once` processing is used as a substitute for
service progress. Full-system drills need the public worker probe; local concurrent
process tests are separate evidence. Do not print/paste proof files or raw logs.

## 7. SQLite snapshot and separate restore rehearsal

WAL must stay on local single-host storage, never NFS, S3 or multi-host mounts.
No replica API topology or HA is claimed. CaseService commits all domain/event/
audit/effect data transactionally. Deployment's SQLite FULL-sync proposal is for
the integration owner; it has not been applied here. A process restart alone does
not prove power-loss durability; reboot/restore are distinct checks.

`backup.py` uses the [SQLite online backup API](https://www.sqlite.org/backup.html)
for committed consistent copies while the API/worker continue writing. It checks
integrity/FKs/required tables, creates mode-0600 standalone snapshots without WAL
requirements, fsyncs and publishes atomically. A bounded failed copy is never
published. The source opens read-only; WAL sidecar housekeeping needs state-directory
access. Health checks likewise do not write household rows.

After public household proof has passed, take a fresh snapshot; from target:

```sh
sudo systemctl start stillhere-backup.service
sudo systemctl show stillhere-backup.service -p Result -p ExecMainStatus
sudo -u stillhere /usr/bin/python3 deploy/backup_status.py
sudo -u stillhere ls -t /var/backups/stillhere/*.sqlite3
```

Select the newest successfully completed filename; do not use a `.partial` file.
Compute/record its trusted SHA-256 (contents are never printed). Transfer only the
synthetic proof state securely from Mac to a PRIVATE target staging directory so
CaseService can verify the restored copy. This is not a developer credential:

```sh
sudo install -d -o stillhere -g stillhere -m 0700 /var/lib/stillhere-restore-stage
# User transfers households.json securely; then ownership/mode on target:
sudo chown stillhere:stillhere /var/lib/stillhere-restore-stage/households.json
sudo chmod 0600 /var/lib/stillhere-restore-stage/households.json
sudo -u stillhere sha256sum /var/backups/stillhere/SELECTED_SNAPSHOT.sqlite3
sudo -u stillhere /opt/stillhere/current/.venv/bin/python deploy/backup.py restore \
  --source /var/backups/stillhere/SELECTED_SNAPSHOT.sqlite3 \
  --directory /var/lib/stillhere-restore-stage/restored-UNIQUE
sudo -u stillhere /opt/stillhere/current/.venv/bin/python deploy/verify_restore.py \
  --db /var/lib/stillhere-restore-stage/restored-UNIQUE/cases.sqlite3 \
  --state /var/lib/stillhere-restore-stage/households.json
```

Expected `database_copy_ok` and `restore_isolation_durability_replay_ok`. Restore
refuses an existing directory; production database is untouched and API/worker
may keep running. Verifier uses CaseService to verify authorized reads and no-op
replays in the separate location; source must contain the synthetic proof. Record
elapsed restore time (RTO) and backup timestamp age (RPO). To check worker persistence
as well, retain worker proof and use the promotion/public SAME-state drill below.
Do not call a file copy of an active WAL database a consistent backup.

For recovery promotion, stop public intake, API, worker and all data/health timers
and their oneshot services. Verify no active writer/copy process, preserve the
whole existing state directory for rollback, and atomically place the rehearsed
new directory at `/var/lib/stillhere` while stopped:

```sh
sudo systemctl stop caddy stillhere-api.service stillhere-worker.service \
  stillhere-health.timer stillhere-backup.timer stillhere-backup-status.timer \
  stillhere-tls-health.timer stillhere-tls-renew.timer
sudo systemctl stop stillhere-health.service stillhere-backup.service \
  stillhere-backup-status.service stillhere-tls-health.service stillhere-tls-renew.service
sudo mv /var/lib/stillhere /var/lib/stillhere-before-restore-UNIQUE
sudo mv /var/lib/stillhere-restore-stage/restored-UNIQUE /var/lib/stillhere
sudo systemctl start stillhere-api.service
sudo systemctl start stillhere-health.service
sudo systemctl start caddy
```

Run Mac public TLS + SAME households `--resume` and SAME worker wait after starting
an accepted worker; a snapshot must contain the observed worker proof if identical
effects are expected. Restart all previous enabled timers and only the accepted
worker. No old WAL/SHM files may be placed beside replacement database. Additive
migrations require the corresponding compatible release; rollback of code does
not reverse database migrations. Clients may have newer commands/tokens than the
backup; communicate RPO and reconcile, never blindly replay changed intent.

## 8. Retention and complete host-loss recovery

Hourly backups target about one hour RPO while successful; alert after two missed
hours and below 20% free disk. Timers monitor newest snapshot age/capacity every
15 minutes. Automatic local deletion is deliberately gated by verified off-host
recovery; otherwise local snapshots accumulate. Address capacity before enabling
long-running intake. Suggested policy pending user acceptance: latest 48h local;
7 daily and 4 weekly off-host copies, with privacy/deletion requirements reviewed.

Select **existing separately accessible Akamai storage** or explicitly authorize
new paid recovery storage first. Use a reviewed encrypted tool such as restic with
separate backup identity/key; no plaintext upload or shared Bedrock credentials.
[Restic's S3-compatible repository guide](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html#s3-compatible-storage)
explains selected Akamai endpoint/bucket configuration; keep the bucket private.
The user configures recovery authentication externally on the server/recovery host
with restic's supported credential mechanism. No credential value appears below:

```sh
# Only after destination/access/key escrow are selected and authorized.
# repository and password files are user-provisioned on SERVER, root-owned 0600.
restic --repository-file /etc/stillhere-recovery/repository \
  --password-file /etc/stillhere-recovery/password init
restic --repository-file /etc/stillhere-recovery/repository \
  --password-file /etc/stillhere-recovery/password backup \
  /var/backups/stillhere/SELECTED_SNAPSHOT.sqlite3 --tag stillhere-verified-sqlite
restic --repository-file /etc/stillhere-recovery/repository \
  --password-file /etc/stillhere-recovery/password check --read-data
restic --repository-file /etc/stillhere-recovery/repository \
  --password-file /etc/stillhere-recovery/password restore SELECTED_RESTIC_SNAPSHOT_ID \
  --target /var/lib/stillhere-recovery-rehearsal-UNIQUE
```

Run these as the separately authorized recovery operator, with private umask 077.
Do not initialize an existing repository. Select IDs locally; outputs can contain
private paths/metadata and are not chat artifacts. Hash the recovered SQLite file
against its externally retained expected digest, then use section 7's restore and
CaseService verifier into another new directory. Successful upload or restic check
alone is not a restore rehearsal. Only after that rehearsal may retention run:

```sh
restic --repository-file /etc/stillhere-recovery/repository \
  --password-file /etc/stillhere-recovery/password forget --tag stillhere-verified-sqlite \
  --group-by host --keep-daily 7 --keep-weekly 4 --dry-run
# Review chosen points; repeat without --dry-run and with --prune only after acceptance.
```

[Official retention guidance](https://restic.readthedocs.io/en/stable/060_forget.html)
explains grouping. A single timestamped path per snapshot creates one retention
group per path; use `--group-by host` for this single-file upload pattern, after
reviewing all tagged points on that host, so actual pruning is bounded by age.
Use a fixed snapshot directory export if grouping by paths is desired. Do not
prune unrelated archives. Review/record the policy and schedule before automating
transfer/prune; no recovery service or scheduler is configured until selections
and access are supplied.

Local `retention.py` defaults to dry-run. The recovery operator supplies a trusted
mode-0600 receipt (format in the script) listing exact hashes **actually recovered
and verified**, with restore_verified:true and verified_at within seven days.
Stop the local backup timer/service during review/application:

```sh
sudo systemctl stop stillhere-backup.timer stillhere-backup.service
sudo -u stillhere /usr/bin/python3 deploy/retention.py --directory /var/backups/stillhere \
  --receipt /var/lib/stillhere-restore-stage/recovery-receipt.json
# After reviewing eligible count, repeat with --apply; then restart backup.timer.
```

Only matching listed files older than 48h are eligible; newest is always preserved.
Unverified/mismatched/unlisted files are never silently deleted. The receipt is
operator evidence, not an authenticated statement from a remote storage provider.
No retention/recovery readiness is claimed without user selection and rehearsal.

Host-loss drill on an approved separate Akamai recovery machine: obtain the immutable
release/wheelhouse/trusted digests and OS/package records from off-host storage;
provision a compatible confirmed host, install offline dependency locks, retrieve/
decrypt the selected snapshot, verify digest, restore to a new location and run
CaseService household/replay checks. Reprovision server-only provider credentials
via the approved identity process, never recovered developer files. Reissue ACME
certificate for the **new** public IP if needed; the hardcoded Caddy configs,
SAN/health verifiers and fixed lineage must be reviewed for that new IP before
exposure. Retain SSH host key/console access, firewall inventory, recovery key
escrow and runbook **outside the lost host**. Measure RPO/RTO, validate trusted
TLS + public replay + accepted worker progress before routing traffic. A local
restore rehearsal is not host-loss proof. Akamai instance Backups, if separately
selected, are supplementary to application-consistent snapshots.

## 9. Cutover, rollback and credentialed model proof

Before a new release, obtain integrated signoff and accepted worker/concurrency
review for its exact hashes. Stop Caddy intake, allow current work to finish, stop
API/worker, take a fresh consistent snapshot and retain old release ID. Install/
verify the new release/venv at a NEW path. Switch `current` through a new symlink
and same-filesystem rename while services are stopped:

```sh
sudo ln -s /opt/stillhere/releases/NEXT_RELEASE_ID /opt/stillhere/current.next
sudo mv -Tf /opt/stillhere/current.next /opt/stillhere/current
sudo systemctl start stillhere-api.service
sudo systemctl start stillhere-health.service
sudo systemctl start caddy
```

Repeat SAME public household proof, TLS and accepted worker drills; restore all
previous timers. If checks fail, stop all writers and switch back; if schema/data
is incompatible, use pre-cutover snapshot with separate restore/rehearsal, accepting
its RPO. There is no zero-downtime/drain guarantee for current daemon model threads.
The exact server/runtime/FULL-sync patch proposals under `deploy/proposals/` are
for integration-owner review, not silently assumed deployed fixes.

Credentialed Bedrock is user-run only through the server's provisioned chain.
The integration owner's accepted smoke command and enabled tool selection must
match the final release. A systemd transient unit can mount the same credential
chain without printing or copying it into shell environment:

```sh
sudo systemd-run --wait --collect --unit=stillhere-bedrock-proof \
  -p User=stillhere -p Group=stillhere -p UMask=0077 \
  -p WorkingDirectory=/opt/stillhere/current \
  -p EnvironmentFile=/etc/stillhere/runtime.conf \
  -p LoadCredential=aws-credentials:/etc/stillhere/aws-credentials \
  -p 'Environment=AWS_SHARED_CREDENTIALS_FILE=%d/aws-credentials AWS_CONFIG_FILE=/dev/null AWS_EC2_METADATA_DISABLED=true PYTHONDONTWRITEBYTECODE=1' \
  -p 'UnsetEnvironment=AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_PROFILE PYTHONPATH PYTHONHOME' \
  -p StandardOutput=null -p StandardError=null -p LimitCORE=0 \
  /opt/stillhere/current/.venv/bin/python -m backend.stillhere.agent.smoke \
  --log-file /var/lib/stillhere-restore-stage/bedrock-proof-UNIQUE.jsonl
sudo -u stillhere /usr/bin/python3 -c 'import json; from pathlib import Path; rows=[json.loads(line) for line in Path("/var/lib/stillhere-restore-stage/bedrock-proof-UNIQUE.jsonl").read_text().splitlines()]; assert rows[-1]["event"] == "smoke_passed" and rows[-1]["mode"] == "default"; assert {"model_invocation_complete", "tool_call_complete", "run_complete"} <= {row["event"] for row in rows}; print("bedrock_saved_reply_replay_ok")'
```

Confirm accepted smoke CLI/report path with integration before running; use its
fixed-label safe report/saved reply/replay assertions. Exit zero alone does not
prove the required tool workflow if that smoke has changed. No `--env-file`, live
provider run or credential inspection is performed by this task.

Retain only redacted evidence: accepted hashes, public certificate metadata,
fixed pass/fail labels/counts, service Results, tested OS/runtime versions and
measured timings. Never attach household tokens/case snapshots, credentials,
raw provider diagnostics or process environments. Dispose synthetic state through
the operator's secure cleanup process; server-side synthetic case removal still
requires an integration-owned authorized cleanup operation, never ad hoc SQL.
