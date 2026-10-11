"""Deployment-only checks: synthetic config, fresh storage, no provider/secret reads."""
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile
import subprocess
from datetime import datetime, timedelta, timezone
import hashlib

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "deploy" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backup = load("backup")
build_release = load("build_release")
verify_release = load("verify_release")
verify_http = load("verify_http")
run_worker = load("run_worker")
tls_publish = load("tls_publish")
retention = load("retention")
backup_status = load("backup_status")
verify_restore = load("verify_restore")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def service(self, name="source/cases.sqlite3"):
        from backend.stillhere.service import CaseService
        return CaseService(self.directory / name)

    def create(self, service):
        token = service.create_session()["session_token"]
        body = {"contract_version": "0.1", "event_id": "deploy_create", "time_zone": "America/Chicago"}
        result = service.create_case(token, body)
        return token, body, result["case_snapshot"]

    def test_restart_preserves_sessions_events_and_isolation(self):
        service = self.service()
        token, body, snapshot = self.create(service)
        reopened = self.service()
        self.assertEqual(snapshot, reopened.read_case(token, snapshot["case_id"]))
        self.assertEqual("already_applied", reopened.create_case(token, body)["status"])
        from backend.stillhere.service import ServiceError
        outsider = reopened.create_session()["session_token"]
        with self.assertRaises(ServiceError) as caught:
            reopened.read_case(outsider, snapshot["case_id"])
        self.assertEqual(404, caught.exception.status)

    def test_online_wal_backup_and_restore_keep_latest_committed_data(self):
        service = self.service()
        token, body, snapshot = self.create(service)
        with closing(sqlite3.connect(service.path)) as hold:
            hold.execute("PRAGMA journal_mode=WAL")
            hold.execute("BEGIN")
            hold.execute("SELECT 1 FROM cases").fetchone()
            command = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "deploy_fact",
                       "expected_case_version": 1, "occurred_at": "2026-10-11T12:00:00Z", "channel": "dashboard", "type": "fact.correct",
                       "payload": {"fact_key": "mobility", "value": "no_car", "observed_at": "2026-10-11T12:00:00Z"}}
            changed = service.execute(token, command)
            self.assertTrue(Path(str(service.path) + "-wal").exists())
            archive = backup.backup(service.path, self.directory / "backups")
        self.assertEqual(0o600, archive.stat().st_mode & 0o777)
        target = self.directory / "restored"
        backup.restore(archive, target)
        restored = self.service("restored/cases.sqlite3")
        self.assertEqual(changed["case_snapshot"], restored.read_case(token, snapshot["case_id"]))
        self.assertEqual("already_applied", restored.execute(token, command)["status"])
        self.assertEqual("already_applied", restored.create_case(token, body)["status"])
        with self.assertRaises(FileExistsError):
            backup.restore(archive, target)

    def test_missing_or_corrupt_source_never_publishes_a_backup(self):
        directory = self.directory / "backups"
        with self.assertRaises(sqlite3.Error):
            backup.backup(self.directory / "missing.sqlite3", directory)
        self.assertFalse(list(directory.iterdir()))
        corrupt = self.directory / "invalid.sqlite3"
        corrupt.write_bytes(b"synthetic invalid database")
        with self.assertRaises(sqlite3.Error):
            backup.restore(corrupt, self.directory / "restored")
        self.assertFalse((self.directory / "restored").exists())

    def test_backup_is_bounded(self):
        service = self.service()
        self.create(service)
        output = self.directory / "output.sqlite3"
        with self.assertRaises(TimeoutError):
            backup.copy_database(service.path, output, timeout=0)
        self.assertFalse(output.exists())

    def test_release_determinism_integrity_and_allowlist(self):
        # Fake wheels exercise packaging only; they are never installed or called real SDK evidence.
        wheelhouse = self.directory / "wheels"
        wheelhouse.mkdir()
        for name, version in (("strands_agents", "1.59.0"), ("python_dotenv", "1.2.2")):
            with zipfile.ZipFile(wheelhouse / f"{name}-{version}-py3-none-any.whl", "w") as wheel:
                wheel.writestr(f"{name}-{version}.dist-info/METADATA", f"Name: {name}\nVersion: {version}\n")
        first, second = self.directory / "one.tar.gz", self.directory / "two.tar.gz"
        one = build_release.build(ROOT, first, wheelhouse, "synthetic-revision")
        two = build_release.build(ROOT, second, wheelhouse, "synthetic-revision")
        self.assertEqual(one, two)
        extract = self.directory / "release"
        with tarfile.open(first) as archive:
            names = archive.getnames()
            self.assertIn("contracts/case-service.schema.json", names)
            self.assertIn("deploy/systemd/caddy.service.d.conf", names)
            self.assertIn("deploy/Caddyfile.bootstrap", names)
            self.assertIn("docs/parallel/deployment-final-handoff.md", names)
            self.assertFalse(any(".env" in n or n.startswith(("var/", ".references/", "frontend/")) for n in names))
            self.assertFalse(any("__pycache__" in n or n.startswith(".venv/") for n in names))
            archive.extractall(extract, filter="data")
        verify_release.verify(extract)
        (extract / "backend/stillhere/server.py").write_text("synthetic tamper")
        with self.assertRaises(ValueError):
            verify_release.verify(extract)

    def test_worker_requires_accepted_module_and_uses_fixed_private_db(self):
        for value in ("", "backend.stillhere.server", "backend.stillhere.agent.smoke", "outside.worker", "backend.stillhere.synthetic_worker", "backend.stillhere.worker;other"):
            with patch.dict(os.environ, {"STILLHERE_WORKER_MODULE": value}, clear=True):
                with self.assertRaises(SystemExit):
                    run_worker.main()
        with patch.dict(os.environ, {"STILLHERE_WORKER_MODULE": "backend.stillhere.worker"}, clear=True):
            with patch.object(run_worker.os, "execv") as execute:
                run_worker.main()
        self.assertEqual([sys.executable, "-m", "backend.stillhere.worker", "--db", "/var/lib/stillhere/cases.sqlite3"], execute.call_args.args[1])

    def test_two_household_verifier_contract_without_http_transport(self):
        from backend.stillhere.service import ServiceError
        service = self.service()
        def call(base, path, body=None, token=None):
            try:
                if path == "/health":
                    return 200, {"status": "ok", "contract_version": "0.1"}
                if path == "/v1/sessions":
                    return 201, service.create_session()
                if path == "/v1/cases":
                    return 200, service.create_case(token, body)
                if path == "/v1/commands":
                    result = service.execute(token, body)
                    codes = {issue["code"] for issue in result["issues"]}
                    status = 404 if "case_unavailable" in codes else 403 if "channel_forbidden" in codes else 200
                    return status, result
                if path == "/v1/operator/queue":
                    return 200, service.read_operator_queue(token)
                return 200, service.read_case(token, path.rsplit("/", 1)[1])
            except ServiceError as error:
                return error.status, {"contract_version": "0.1", "error": error.issue}
        with patch.object(verify_http, "call", side_effect=call):
            state = self.directory / "proof.json"
            verify_http.verify("https://172.238.189.78", state)
            verify_http.verify("https://172.238.189.78", state, True)
            archive = backup.backup(service.path, self.directory / "copied")
            backup.restore(archive, self.directory / "second_location")
            verify_restore.verify(self.directory / "second_location/cases.sqlite3", state)

    def test_remote_proofs_refuse_bearer_redirects_and_plaintext_downgrades(self):
        handler = verify_http.NoRedirect()
        for destination in ("http://172.238.189.78/v1/commands", "https://other.invalid/v1/commands"):
            self.assertIsNone(handler.redirect_request(None, None, 302, None, None, destination))

    def test_independent_worker_processes_produce_one_simulated_effect_set(self):
        from backend.stillhere.service import CaseService
        earlier = datetime.now(timezone.utc) - timedelta(minutes=2)
        stamp = lambda instant: instant.isoformat(timespec="seconds").replace("+00:00", "Z")
        path = self.directory / "worker/cases.sqlite3"
        service = CaseService(path, clock=lambda: stamp(earlier))
        token, _, snapshot = self.create(service)
        command = {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": "deploy_worker_enroll",
                   "expected_case_version": 1, "occurred_at": stamp(earlier), "channel": "dashboard", "type": "check_in.enroll",
                   "payload": {"consent": True, "follow_up_consent": True, "due_at": stamp(earlier+timedelta(seconds=30)),
                               "time_zone": "America/Chicago", "grace_minutes": 0, "channel": "in_app"}}
        self.assertEqual("applied", service.execute(token, command)["status"])
        args = [sys.executable, "-B", "-m", "backend.stillhere.worker", "--db", str(path), "--once"]
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        processes = [subprocess.Popen(args, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        counts = []
        for process in processes:
            output, _ = process.communicate(timeout=20)
            self.assertEqual(0, process.returncode)
            result = json.loads(output)
            self.assertIs(result["simulation"], True)
            counts.append(result["processed_cases"])
        self.assertEqual(1, sum(counts))
        reopened = CaseService(path)
        before = reopened.read_case(token, snapshot["case_id"])
        self.assertEqual(1, len(before["check_in"]["attempts"]))
        self.assertEqual(1, len(before["follow_ups"]))
        subprocess.run(args, cwd=ROOT, env=environment, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        self.assertEqual(before, CaseService(path).read_case(token, snapshot["case_id"]))

    def test_tls_reload_failure_restores_previous_atomic_pair(self):
        root, lineage = self.directory / "tls", self.directory / "lineage"
        root.mkdir()
        (root / "previous").mkdir()
        (root / "current").symlink_to("previous")
        lineage.mkdir()
        for name in ("fullchain.pem", "privkey.pem"):
            (lineage / name).write_bytes(b"synthetic material; never a real credential")
        reloads = []
        def run(command, **kwargs):
            if command[:2] == ["systemctl", "reload"]:
                reloads.append(command)
                if len(reloads) == 1:
                    raise RuntimeError("synthetic reload failure")
            return b"synthetic identical public keys"
        with patch.object(tls_publish, "ROOT", root), patch.object(tls_publish, "LINEAGE", lineage), \
             patch.object(tls_publish.os, "geteuid", return_value=0), patch.object(tls_publish.os, "chown"), \
             patch.object(tls_publish.grp, "getgrnam") as group, patch.object(tls_publish, "run", side_effect=run), \
             patch.dict(os.environ, {}, clear=True):
            group.return_value.gr_gid = os.getgid()
            with self.assertRaises(RuntimeError):
                tls_publish.publish()
        self.assertEqual("previous", os.readlink(root / "current"))
        self.assertEqual(2, len(reloads))
        self.assertFalse(list(root.glob("pair-*")))

    def test_retention_requires_recent_restored_copy_and_matching_digest(self):
        directory = self.directory / "backups"
        directory.mkdir()
        old = directory / "20260101T000000000000Z.sqlite3"
        latest = directory / "20260102T000000000000Z.sqlite3"
        old.write_bytes(b"synthetic backup")
        latest.write_bytes(b"synthetic latest")
        os.utime(old, (0, 0))
        os.utime(latest, (0, 0))
        receipt = self.directory / "receipt.json"
        proof = {"restore_verified": True, "verified_at": datetime.now(timezone.utc).isoformat(),
                 "sha256": {old.name: hashlib.sha256(old.read_bytes()).hexdigest(), latest.name: hashlib.sha256(latest.read_bytes()).hexdigest()}}
        receipt.write_text(json.dumps(proof))
        self.assertEqual(1, retention.prune(directory, receipt))
        self.assertTrue(old.exists())
        self.assertEqual(1, retention.prune(directory, receipt, True))
        self.assertFalse(old.exists())
        self.assertTrue(latest.exists())
        proof["restore_verified"] = False
        receipt.write_text(json.dumps(proof))
        with self.assertRaises(ValueError):
            retention.prune(directory, receipt, True)
        with self.assertRaises(ValueError):
            backup_status.check(directory)

    def test_smoke_rejects_plaintext_remote_without_a_network_call(self):
        with patch.object(verify_http, "call") as call:
            with self.assertRaises(ValueError):
                verify_http.verify("http://synthetic.example", self.directory / "state.json")
        call.assert_not_called()

    def test_http_restart_smoke_with_disposable_households(self):
        from backend.stillhere.server import CaseHTTPServer
        service = self.service()
        state = self.directory / "synthetic-state.json"
        for resume in (False, True):
            # Reuse the same origin after restart, with the same DB and new service.
            if resume:
                service = self.service()
            server = CaseHTTPServer(("127.0.0.1", port if resume else 0), service)
            port = server.server_port
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                verify_http.verify(f"http://127.0.0.1:{port}", state, resume)
                self.assertEqual(0o600, state.stat().st_mode & 0o777)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
