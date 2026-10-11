"""Scoped SQLite case writes. Providers and clients never write storage directly."""

import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .commands import assistant_turn_id, COMMAND_HANDLERS, apply_command, validate_payload, with_intake
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
                CREATE TABLE IF NOT EXISTS agent_runs (
                    case_id TEXT NOT NULL REFERENCES cases(case_id), event_id TEXT NOT NULL,
                    run_digest TEXT NOT NULL, expires_at TEXT NOT NULL, state TEXT NOT NULL,
                    PRIMARY KEY (case_id, event_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_running_agent_per_case
                    ON agent_runs(case_id) WHERE state='running';
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
                if event_id.startswith(("agent_tool_", "agent_state_")):
                    raise ServiceError(400, "reserved_event_id", "Agent event prefixes are reserved for backend-generated identities.")
                return self._execute(connection, owner, command, event_id, now)
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(event_id, now, error)

    def _execute(self, connection, owner, command, event_id, now):
        validate("CommandEnvelope", command)
        snapshot = self._snapshot(connection, owner, command["case_id"])
        if command["channel"] in ("operator", "system"):
            raise ServiceError(403, "channel_forbidden", "This session has household authority only.")
        if command["type"] not in COMMAND_HANDLERS:
            raise ServiceError(400, "unsupported_command", "This command is not implemented yet.")
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
        if command["type"] == "conversation.message" and (
            command["payload"]["message_id"] == assistant_turn_id(command["case_id"], event_id)
            or any(turn["id"] == command["payload"]["message_id"] for turn in snapshot["conversation"]["turns"])
        ):
            raise ServiceError(400, "message_id_reused", "Changed or repeated message identity requires the original event_id.")
        before_case = canonical_json(snapshot)
        before = snapshot["facts"].get(command["payload"]["fact_key"]) if command["type"] == "fact.correct" else None
        snapshot = apply_command(snapshot, command, now)
        connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), command["case_id"]))
        connection.execute(
            "UPDATE events SET applied_version=?, applied_received_at=?, before_fact_json=?, before_case_json=? WHERE case_id=? AND event_id=?",
            (snapshot["case_version"], now, canonical_json(before), before_case, command["case_id"], event_id),
        )
        return self._result(event_id, "applied", now, snapshot, snapshot["case_version"])

    def _save_agent_state(self, connection, snapshot, turn, state, now, text="", issue=None):
        """Internal audited transition; never accepts model-selected snapshot fields."""
        before = canonical_json(snapshot)
        turn.update(state=state, text=text)
        if issue is not None:
            turn["issue"] = issue
        snapshot["case_version"] += 1
        snapshot["updated_at"] = now
        validate("CaseSnapshot", snapshot)
        internal_id = "agent_state_" + self._fingerprint([turn["id"], state])[:32]
        transition = {"type": "conversation.turn_state", "turn_id": turn["id"], "state": state}
        connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), snapshot["case_id"]))
        connection.execute(
            "INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at,applied_received_at,applied_version,before_case_json) VALUES (?,?,?,?,?,?,?,?)",
            (snapshot["case_id"], internal_id, self._fingerprint(transition), canonical_json(transition), now, now, snapshot["case_version"], before),
        )

    @staticmethod
    def _agent_turn(snapshot, event_id):
        return next((t for t in snapshot["conversation"]["turns"] if t.get("event_id") == event_id and t["role"] == "assistant"), None)

    def _expire_agent_runs(self, connection, snapshot, now):
        for row in connection.execute("SELECT * FROM agent_runs WHERE case_id=? AND state='running'", (snapshot["case_id"],)).fetchall():
            if datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) > datetime.fromisoformat(now.replace("Z", "+00:00")):
                continue
            turn = self._agent_turn(snapshot, row["event_id"])
            self._save_agent_state(connection, snapshot, turn, "failed", now, issue={
                "code": "agent_interrupted", "message": "The agent run expired. Accepted changes remain saved; send a new message to continue.", "retryable": False,
            })
            connection.execute("UPDATE agent_runs SET state='failed' WHERE case_id=? AND event_id=?", (snapshot["case_id"], row["event_id"]))

    def claim_agent_turn(self, token, case_id, event_id, timeout_seconds):
        """One durable claim per turn, and one active agent per case across processes."""
        now = self.clock()
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                self._expire_agent_runs(connection, snapshot, now)
                turn = self._agent_turn(snapshot, event_id)
                if turn is None or turn["state"] != "queued":
                    return None
                if connection.execute("SELECT 1 FROM agent_runs WHERE case_id=? AND state='running'", (case_id,)).fetchone():
                    return None
                # Preserve arrival order if several HTTP clients queue messages together.
                first = next(t for t in snapshot["conversation"]["turns"] if t["role"] == "assistant" and t["state"] == "queued")
                if first["id"] != turn["id"]:
                    return None
                run_id = secrets.token_hex(32)
                expires_at = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=timeout_seconds)).isoformat().replace("+00:00", "Z")
                connection.execute("INSERT INTO agent_runs VALUES (?,?,?,?,?)", (case_id, event_id, self._fingerprint(run_id), expires_at, "running"))
                self._save_agent_state(connection, snapshot, turn, "running", now)
                parent = connection.execute("SELECT command_json FROM events WHERE case_id=? AND event_id=?", (case_id, event_id)).fetchone()
                return {"run_id": run_id, "snapshot": snapshot, "command": json.loads(parent["command_json"])}
        except sqlite3.Error:
            raise ServiceError(503, "storage_unavailable", "Agent state storage is unavailable.", True) from None

    def _active_run(self, connection, case_id, event_id, run_id, now, allow_expired=False):
        row = connection.execute("SELECT * FROM agent_runs WHERE case_id=? AND event_id=? AND run_digest=? AND state='running'", (case_id, event_id, self._fingerprint(run_id))).fetchone()
        if row is None or (not allow_expired and datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00")) <= datetime.fromisoformat(now.replace("Z", "+00:00"))):
            raise ServiceError(409, "agent_run_inactive", "This agent run can no longer change the case.")

    def execute_agent_command(self, token, case_id, parent_event_id, run_id, command_type, payload, expected_version):
        """Lease check and ordinary command commit share a transaction; late tools cannot write."""
        now = self.clock()
        child_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, command_type, payload])[:48]
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                if command_type not in ("fact.correct", "intake.submit"):
                    raise ServiceError(400, "tool_forbidden", "This agent tool is not permitted.")
                parent = json.loads(connection.execute("SELECT command_json FROM events WHERE case_id=? AND event_id=?", (case_id, parent_event_id)).fetchone()["command_json"])
                command = {
                    "contract_version": VERSION, "case_id": case_id, "event_id": child_id,
                    "expected_case_version": expected_version, "occurred_at": parent["occurred_at"],
                    "channel": "chat", "type": command_type, "payload": payload,
                }
                return self._execute(connection, owner, command, child_id, now)
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(child_id, now, error)

    def finish_agent_turn(self, token, case_id, event_id, run_id, text="", issue=None):
        now = self.clock()
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                # The owning runtime can record a failure after its deadline. Late
                # success and domain writes remain forbidden; another process's
                # expiration remains terminal. Preserve the actual timeout cause.
                if issue is None:
                    self._expire_agent_runs(connection, snapshot, now)
                turn = self._agent_turn(snapshot, event_id)
                if turn is None or turn["state"] != "running":
                    return snapshot
                self._active_run(connection, case_id, event_id, run_id, now, allow_expired=issue is not None)
                state = "failed" if issue else "complete"
                self._save_agent_state(connection, snapshot, turn, state, now, text, issue)
                connection.execute("UPDATE agent_runs SET state=? WHERE case_id=? AND event_id=?", (state, case_id, event_id))
                return snapshot
        except sqlite3.Error:
            raise ServiceError(503, "storage_unavailable", "Agent result storage is unavailable.", True) from None

    def commit_agent_incident_context(self, token, case_id, parent_event_id, run_id, result, expected_version):
        """Internal C03 commit: a server-produced result, never a public/model snapshot write."""
        from .incidents import build_query, query_identity
        now = self.clock()
        child_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, "incident.context"])[:48]
        try:
            validate("IncidentContext", result)
            child_id = "agent_tool_" + self._fingerprint([case_id, parent_event_id, "incident.context", query_identity(result["query"])])[:48]
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                existing = connection.execute("SELECT applied_version FROM events WHERE case_id=? AND event_id=?", (case_id, child_id)).fetchone()
                if existing:
                    return self._result(child_id, "already_applied", now, snapshot, existing["applied_version"])
                query = result["query"]
                current_query = build_query(snapshot, {"location_scope": query["location_scope"], "lookback_days": query["lookback_days"]}, now)
                if (expected_version != snapshot["case_version"] or result["input_case_version"] != expected_version
                        or query_identity(query) != query_identity(current_query)):
                    return self._result(child_id, "conflict", now, snapshot, issue={
                        "code": "version_conflict", "message": "Case inputs changed during incident retrieval; reconcile before another write.",
                        "field": "expected_case_version", "retryable": False})
                for provider in result["providers"].values():
                    if any(record["source_id"] != provider["source"]["id"] for record in provider["records"]):
                        raise InvalidInput("$.incident_context", "Incident records must reference their owning provider source.")
                before = canonical_json(snapshot)
                scope = query["location_scope"]
                contexts = snapshot.setdefault("incident_context", {})
                previous = contexts.get(scope)
                old_ids = {value["source"]["id"] for value in previous["providers"].values()} if previous else set()
                contexts[scope] = json.loads(canonical_json(result))
                new_sources = [provider["source"] for provider in result["providers"].values()]
                replaced_ids = old_ids | {source["id"] for source in new_sources}
                snapshot["sources"] = [source for source in snapshot["sources"] if source.get("id") not in replaced_ids] + new_sources
                snapshot["case_version"] += 1
                snapshot["updated_at"] = now
                if snapshot["plan"]["state"] != "not_requested":
                    snapshot["plan"].update(state="pending", pending_input_case_version=snapshot["case_version"])
                if snapshot["finance"]["state"] == "not_calculated":
                    snapshot["finance"]["input_case_version"] = snapshot["case_version"]
                else:
                    snapshot["finance"].update(state="pending", pending_input_case_version=snapshot["case_version"])
                validate("CaseSnapshot", snapshot)
                transition = {"type": "incident.context", "parent_event_id": parent_event_id, "payload": result}
                connection.execute("UPDATE cases SET snapshot_json=? WHERE case_id=?", (canonical_json(snapshot), case_id))
                connection.execute(
                    "INSERT INTO events (case_id,event_id,fingerprint,command_json,first_received_at,applied_received_at,applied_version,before_case_json) VALUES (?,?,?,?,?,?,?,?)",
                    (case_id, child_id, self._fingerprint(query_identity(query)), canonical_json(transition), now, now, snapshot["case_version"], before))
                return self._result(child_id, "applied", now, snapshot, snapshot["case_version"])
        except (InvalidInput, ServiceError, sqlite3.Error) as error:
            return self._failed(child_id, now, error)
