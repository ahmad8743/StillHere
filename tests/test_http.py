import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from backend.stillhere.contracts import validate
from backend.stillhere.server import CaseHTTPServer
from backend.stillhere.service import CaseService


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.server = CaseHTTPServer(("127.0.0.1", 0), CaseService(Path(self.directory.name) / "cases.sqlite3"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, token=None, raw=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json", "X-Contract-Version": "0.1"}
        if token:
            headers["Authorization"] = "Bearer " + token
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        try:
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), dict(response.getheaders())
        finally:
            connection.close()

    def test_real_http_create_correct_read_replay_and_scope(self):
        status, session, _ = self.request("POST", "/v1/sessions", {"contract_version": "0.1"})
        self.assertEqual(status, 201)
        validate("SessionResult", session)
        token = session["session_token"]
        create = {"contract_version": "0.1", "event_id": "create_http", "time_zone": "America/Chicago"}
        status, created, headers = self.request("POST", "/v1/cases", create, token)
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        case_id = created["case_snapshot"]["case_id"]
        command = {
            "contract_version": "0.1", "case_id": case_id, "event_id": "correct_http",
            "expected_case_version": 1, "occurred_at": "2026-10-10T15:00:00Z",
            "channel": "dashboard", "type": "fact.correct",
            "payload": {"fact_key": "mobility", "value": "no_car", "observed_at": "2026-10-10T15:00:00Z"},
        }
        status, result, _ = self.request("POST", "/v1/commands", command, token)
        self.assertEqual(status, 200)
        validate("CommandResult", result)
        status, resumed, _ = self.request("GET", "/v1/cases/" + case_id, token=token)
        self.assertEqual(status, 200)
        self.assertEqual(resumed, result["case_snapshot"])
        self.assertEqual(self.request("POST", "/v1/commands", command, token)[1]["status"], "already_applied")
        conflicting = dict(command, event_id="new_correction")
        self.assertEqual(self.request("POST", "/v1/commands", conflicting, token)[0], 409)
        stranger = self.request("POST", "/v1/sessions", {"contract_version": "0.1"})[1]["session_token"]
        for private_id in (case_id, "missing_case"):
            status, error, _ = self.request("GET", "/v1/cases/" + private_id, token=stranger)
            self.assertEqual(status, 404)
            validate("AccessError", error)
        status, rejected, _ = self.request("POST", "/v1/commands", command, stranger)
        self.assertEqual(status, 404)
        self.assertIsNone(rejected["case_snapshot"])
        status, rejected, _ = self.request("POST", "/v1/commands", command)
        self.assertEqual(status, 401)
        self.assertIsNone(rejected["case_snapshot"])
        self.assertEqual(self.request("GET", "/health")[1]["implemented_commands"], ["fact.correct"])

    def test_malformed_json_and_self_assigned_roles_are_rejected(self):
        for raw in ('{"role":"operator"}', '{"role":null,"role":"system"}', '{"amount":NaN}', '[]', '{'):
            with self.subTest(raw=raw):
                status, error, _ = self.request("POST", "/v1/sessions", raw=raw)
                self.assertEqual(status, 400)
                validate("AccessError", error)


if __name__ == "__main__":
    unittest.main()
