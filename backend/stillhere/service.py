"""Scoped SQLite case writes. Providers and clients never write storage directly."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .commands import COMMAND_HANDLERS, apply_command, validate_payload, with_intake
from .contracts import InvalidInput, VERSION, canonical_json, empty_case, utc_now, validate


class ServiceError(Exception):
    def __init__(self, status, code, message, retryable=False):
        self.status = status
        self.issue = {"code": code, "message": message, "retryable": retryable}
        super().__init__(message)


class CaseService:
    def __init__(self, database_path, clock=utc_now):
        self.path = Path(database_path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token_digest TEXT PRIMARY KEY, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    owner_digest TEXT NOT NULL REFERENCES sessions(token_digest),
                    snapshot_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS creations (
                    owner_digest TEXT NOT NULL REFERENCES sessions(token_digest),
                    event_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    received_at TEXT NOT NULL,
                    PRIMARY KEY (owner_digest, event_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    case_id TEXT NOT NULL REFERENCES cases(case_id),
                    event_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    first_received_at TEXT NOT NULL,
                    applied_received_at TEXT,
                    applied_version INTEGER,
                    before_fact_json TEXT,
                    before_case_json TEXT,
                    PRIMARY KEY (case_id, event_id)
                );
            """)
        # Additive migration preserves databases created by the first C01 slice.
        with self._transaction() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)")}
            if "before_case_json" not in columns:
                connection.execute("ALTER TABLE events ADD COLUMN before_case_json TEXT")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _fingerprint(value):
        return hashlib.sha256(canonical_json(value).encode()).hexdigest()

    @staticmethod
    def _session(connection, token):
        if not isinstance(token, str) or not 1 <= len(token) <= 128:
            raise ServiceError(401, "unauthorized", "A valid scoped session is required.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not connection.execute("SELECT 1 FROM sessions WHERE token_digest=?", (digest,)).fetchone():
            raise ServiceError(401, "unauthorized", "A valid scoped session is required.")
        return digest

    @staticmethod
    def _snapshot(connection, owner_digest, case_id):
        row = connection.execute(
            "SELECT snapshot_json FROM cases WHERE case_id=? AND owner_digest=?", (case_id, owner_digest)
        ).fetchone()
        if not row:
            raise ServiceError(404, "case_unavailable", "Case is unavailable to this session.")
        return json.loads(row["snapshot_json"])

    @staticmethod
    def _event_id(request):
        event_id = request.get("event_id") if isinstance(request, dict) else None
        try:
            validate("Id", event_id)
        except InvalidInput:
            raise ServiceError(400, "invalid_request", "A valid event_id is required.") from None
        return event_id

    @staticmethod
    def _result(event_id, status, received_at, snapshot=None, applied_version=None, issue=None):
        result = {
            "contract_version": VERSION, "event_id": event_id, "status": status,
            "received_at": received_at, "applied_case_version": applied_version,
            "case_snapshot": snapshot, "issues": [issue] if issue else [],
        }
        validate("CommandResult", result)
        if snapshot is not None:
            validate("CaseSnapshot", snapshot)
        return result

    def _failed(self, event_id, now, error):
        if isinstance(error, InvalidInput):
            issue = {"code": "invalid_input", "message": str(error), "field": error.field, "retryable": False}
        elif isinstance(error, ServiceError):
            issue = error.issue
        else:
            issue = {"code": "storage_unavailable", "message": "Case storage is unavailable; retry the same event.", "retryable": True}
        status = "unavailable" if issue["retryable"] else "rejected"
        return self._result(event_id, status, now, issue=issue)

    def create_session(self):
        token, now = "session_" + secrets.token_urlsafe(32), self.clock()
        try:
            with self._transaction() as connection:
                connection.execute("INSERT INTO sessions VALUES (?, ?)", (hashlib.sha256(token.encode()).hexdigest(), now))
        except sqlite3.Error:
            raise ServiceError(503, "storage_unavailable", "Session storage is unavailable.", True) from None
        result = {"contract_version": VERSION, "session_token": token, "created_at": now}
        validate("SessionResult", result)
        return result

    def create_case(self, token, request):
        event_id, now = self._event_id(request), self.clock()
        try:
            with self._transaction() as connection:
                owner = self._session(connection, token)
                validate("CreateCaseRequest", request)
                fingerprint = self._fingerprint(request)
                previous = connection.execute(
                    "SELECT * FROM creations WHERE owner_digest=? AND event_id=?", (owner, event_id)
                ).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise ServiceError(400, "event_id_reused", "Changed intent requires a new event_id.")
                    snapshot = self._snapshot(connection, owner, previous["case_id"])
                    return self._result(event_id, "already_applied", now, snapshot, 1)
                case_id = "case_" + secrets.token_hex(16)
                snapshot = empty_case(case_id, request["time_zone"], now)
                if "intake" in request:
                    snapshot = with_intake(snapshot, request["intake"], request.get("occurred_at", now))
                connection.execute("INSERT INTO cases VALUES (?, ?, ?)", (case_id, owner, canonical_json(snapshot)))
                connection.execute("INSERT INTO creations VALUES (?, ?, ?, ?, ?)", (owner, event_id, fingerprint, case_id, now))
                return self._result(event_id, "applied", now, snapshot, 1)
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(event_id, now, error)

    def read_case(self, token, case_id, contract_version=VERSION):
        try:
            with self._connection() as connection:
                owner = self._session(connection, token)
                if contract_version != VERSION:
                    raise ServiceError(400, "unsupported_contract", "Read requests require contract version 0.1.")
                return self._snapshot(connection, owner, case_id)
        except sqlite3.Error:
            raise ServiceError(503, "storage_unavailable", "Case storage is unavailable.", True) from None

    def execute(self, token, command):
        event_id, now = self._event_id(command), self.clock()
        try:
            with self._transaction() as connection:
                owner = self._session(connection, token)
                validate("CommandEnvelope", command)
                snapshot = self._snapshot(connection, owner, command["case_id"])
                if command["channel"] in ("operator", "system"):
                    raise ServiceError(403, "channel_forbidden", "This session has household authority only.")
                if command["type"] not in COMMAND_HANDLERS:
                    raise ServiceError(400, "unsupported_command", "This slice implements fact.correct and intake.submit only.")
                validate_payload(command["type"], command["payload"])
                logical = {key: value for key, value in command.items() if key != "expected_case_version"}
                fingerprint = self._fingerprint(logical)
                previous = connection.execute(
                    "SELECT * FROM events WHERE case_id=? AND event_id=?", (command["case_id"], event_id)
                ).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise ServiceError(400, "event_id_reused", "Changed intent requires a new event_id.")
                    if previous["applied_version"] is not None:
                        return self._result(event_id, "already_applied", now, snapshot, previous["applied_version"])
                else:
                    connection.execute(
                        "INSERT INTO events (case_id, event_id, fingerprint, command_json, first_received_at) VALUES (?, ?, ?, ?, ?)",
                        (command["case_id"], event_id, fingerprint, canonical_json(logical), now),
                    )
                if command["expected_case_version"] != snapshot["case_version"]:
                    return self._result(event_id, "conflict", now, snapshot, issue={
                        "code": "version_conflict", "message": "Read and reconcile the latest case before retrying.",
                        "field": "expected_case_version", "retryable": False,
                    })
                before_case = canonical_json(snapshot)
                before = snapshot["facts"].get(command["payload"]["fact_key"]) if command["type"] == "fact.correct" else None
                snapshot = apply_command(snapshot, command, now)
                connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), command["case_id"]))
                connection.execute(
                    "UPDATE events SET applied_version=?, applied_received_at=?, before_fact_json=?, before_case_json=? WHERE case_id=? AND event_id=?",
                    (snapshot["case_version"], now, canonical_json(before), before_case, command["case_id"], event_id),
                )
                return self._result(event_id, "applied", now, snapshot, snapshot["case_version"])
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(event_id, now, error)
