"""CaseService extension: separate public candidates/catalogs, private replay links.

All writes run on CaseService's transaction. Local manual review requires an
OS-admin capability object; it is never exposed through household HTTP/tools.
"""

import copy
import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass

from ..contracts import InvalidInput, VERSION, canonical_json, validate
from .official import source_registry, validate_fetch
from .rules import ProgramRuleStore, _instant, build_query, notice, validate_catalog


def service_error(status, code, message, retryable=False):
    from ..service import ServiceError
    return ServiceError(status, code, message, retryable)


@dataclass(frozen=True)
class ManualReviewAuthority:
    """Local process/file authority, not a household role or deployed operator session."""
    reviewer: str

    def __post_init__(self):
        if not isinstance(self.reviewer, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.reviewer):
            raise ValueError("Use an opaque local reviewer tag.")


def require_manual(authority):
    if type(authority) is not ManualReviewAuthority:
        raise service_error(403, "manual_review_required", "Local manual-review authority is required; household sessions cannot publish rules.")


def candidate_from_fetch(identifier, kind, arguments, fetched, now):
    validate("RuleCandidateToolArguments" if kind == "candidate" else "RuleDiscrepancyToolArguments", arguments)
    validate_fetch(fetched)
    if fetched["source_id"] != arguments["source_id"] or fetched["state"] not in ("available", "unavailable"):
        raise InvalidInput("$.source_id", "Review evidence must match the backend-fetched public source.")
    receipt = copy.deepcopy(fetched["receipt"])
    current_live = (fetched["state"] == "available" and receipt is not None
                    and _instant(receipt["retrieved_at"]) <= _instant(now) < _instant(receipt["expires_at"]))
    if kind == "candidate" and (not current_live or not arguments["requirement_keys"]):
        raise InvalidInput("$.receipt", "Rule extraction needs fresh live public evidence and at least one structured requirement.")
    if kind == "discrepancy" and arguments["reason"] == "source_unavailable":
        if fetched["state"] != "unavailable":
            raise InvalidInput("$.reason", "A source-unavailable report needs a failed public request.")
        if "evidence_start" in arguments or "evidence_end" in arguments:
            raise InvalidInput("$.evidence_start", "Failed-source reports carry no claimed live text excerpt.")
        excerpt = None
    else:
        if not current_live:
            raise InvalidInput("$.receipt", "A content discrepancy needs current live public evidence.")
        start, end = arguments.get("evidence_start"), arguments.get("evidence_end")
        if start is None or end is None or not 0 <= start < end <= len(receipt["content"]) or end - start > 800:
            raise InvalidInput("$.evidence_end", "Choose a nonempty public evidence span of at most 800 characters.")
        excerpt = receipt["content"][start:end]
        if not excerpt.strip():
            raise InvalidInput("$.evidence_start", "Public evidence cannot be blank.")
    record = {"id":identifier, "kind":kind, "program_id":arguments["program_id"], "base_version":arguments["base_version"],
              "jurisdiction":{"country":"US", "state":"CO"}, "created_at":now, "revision":1, "review_state":"pending",
              "arguments":copy.deepcopy(arguments), "source_state":fetched["state"], "receipt":receipt, "evidence_excerpt":excerpt}
    validate("RuleReviewCandidate", record)
    return record


def validate_publication(bundle, candidate, base, now):
    validate("RulePublicationBundle", bundle)
    rule, sources = bundle["rule"], bundle["sources"]
    validate_catalog({"version":"manual_review", "rules":[rule], "sources":sources})
    if {source["id"] for source in sources} != set(rule["source_ids"]) or rule["data_mode"] != "cached" or rule["version"].startswith("EDIT_"):
        raise InvalidInput("$.publication", "Manual versions require reviewed cached data, exact attribution and a chosen immutable version.")
    if (rule["id"] != base["id"] or rule["program_id"] != base["program_id"] or rule["jurisdiction"] != base["jurisdiction"]
            or rule["issuer"] != base["issuer"] or rule["version"] == base["version"]):
        raise InvalidInput("$.publication.rule", "Publication must create a new version of the reviewed candidate's existing program/issuer.")
    receipt = candidate["receipt"]
    if candidate["source_state"] != "available" or receipt is None or not _instant(receipt["retrieved_at"]) <= _instant(now) < _instant(receipt["expires_at"]):
        raise InvalidInput("$.publication", "Publication requires fresh live candidate evidence; failed or stale evidence cannot publish policy.")
    if not _instant(receipt["retrieved_at"]) <= _instant(rule["reviewed_at"]) <= _instant(now) < _instant(rule["review_expires_at"]):
        raise InvalidInput("$.publication.rule.reviewed_at", "Manual review must follow evidence retrieval and have a future review expiry.")
    evidence_source = next((source for source in sources if source["id"] == receipt["source_id"]), None)
    if (evidence_source is None or evidence_source.get("content_sha256") != receipt["content_sha256"]
            or evidence_source["retrieved_at"] != receipt["retrieved_at"] or evidence_source["data_mode"] != "cached"):
        raise InvalidInput("$.publication.sources", "The published attribution must include the exact public receipt hash and retrieval time.")
    registry = source_registry()
    for source in sources:
        official = registry.get(source["id"])
        if official is None or source["url"] != official["url"] or source["issuer"] != official["issuer"] or source["jurisdiction"] != official["jurisdiction"]:
            raise InvalidInput("$.publication.sources", "Manual publication uses registered official source identities only.")
        if not _instant(source["retrieved_at"]) <= _instant(source["reviewed_at"]) <= _instant(now) < _instant(source["expires_at"]):
            raise InvalidInput("$.publication.sources", "Every source needs valid, current manual review metadata.")


class KnowledgeServiceMixin:
    def _init_knowledge(self, connection):
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_candidates (
                candidate_id TEXT PRIMARY KEY, record_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_effects (
                case_id TEXT NOT NULL REFERENCES cases(case_id), parent_event_id TEXT NOT NULL,
                effect_key TEXT NOT NULL, candidate_id TEXT NOT NULL REFERENCES knowledge_candidates(candidate_id),
                PRIMARY KEY (case_id,parent_event_id,effect_key)
            );
            CREATE TABLE IF NOT EXISTS knowledge_catalog (
                singleton INTEGER PRIMARY KEY CHECK (singleton=1), catalog_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_versions (
                rule_id TEXT NOT NULL, version TEXT NOT NULL, bundle_json TEXT NOT NULL,
                PRIMARY KEY (rule_id,version)
            );
            CREATE TABLE IF NOT EXISTS knowledge_reviews (
                event_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, reviewer TEXT NOT NULL,
                reviewed_at TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT NOT NULL
            );
        """)

    @staticmethod
    def _catalog_in(connection):
        row = connection.execute("SELECT catalog_json FROM knowledge_catalog WHERE singleton=1").fetchone()
        catalog = json.loads(row["catalog_json"]) if row else ProgramRuleStore._load()
        validate_catalog(catalog)
        return catalog

    def read_program_catalog(self):
        try:
            with self._connection() as connection:
                return self._catalog_in(connection)
        except sqlite3.Error:
            raise OSError("Published knowledge storage unavailable.") from None

    def read_program_version(self, version):
        try:
            with self._connection() as connection:
                bundles = [json.loads(row["bundle_json"]) for row in connection.execute("SELECT bundle_json FROM knowledge_versions WHERE version=?", (version,))]
                rules = [bundle["rule"] for bundle in bundles]
                sources = {source["id"]:source for bundle in bundles for source in bundle["sources"]}
                catalog = {"version":"archive_" + hashlib.sha256(version.encode()).hexdigest()[:32], "rules":rules, "sources":list(sources.values())}
                validate_catalog(catalog)
                return catalog
        except sqlite3.Error:
            raise OSError("Published knowledge history unavailable.") from None

    def submit_agent_knowledge(self, token, case_id, parent_event_id, run_id, kind, arguments, fetched, expected_version, deadline):
        if kind not in ("candidate", "discrepancy"):
            raise service_error(400, "tool_forbidden", "Only separate review submissions are allowed.")
        validate("RuleCandidateToolArguments" if kind == "candidate" else "RuleDiscrepancyToolArguments", arguments)
        effect_key = self._fingerprint([kind, arguments])
        identifier = "candidate_" + self._fingerprint([case_id, parent_event_id, effect_key])[:32]
        try:
            with self._transaction() as connection:
                now = self.clock()
                owner = self._session(connection, token)
                snapshot = self._snapshot(connection, owner, case_id)
                self._active_run(connection, case_id, parent_event_id, run_id, now)
                if time.monotonic() >= deadline:
                    raise service_error(409, "agent_run_inactive", "Expired review submissions cannot commit.")
                result = {"contract_version":VERSION, "state":"submitted", "candidate_id":identifier, "kind":kind,
                          "review_state":"pending", "publication_state":"unpublished", "input_case_version":snapshot["case_version"],
                          "notices":[notice("rule_review_pending", "Public evidence was queued for manual review; no rule, case domain or household eligibility was changed.")]}
                prior = connection.execute("SELECT candidate_id FROM knowledge_effects WHERE case_id=? AND parent_event_id=? AND effect_key=?", (case_id,parent_event_id,effect_key)).fetchone()
                if prior:
                    result.update(state="already_submitted", candidate_id=prior["candidate_id"])
                elif expected_version != snapshot["case_version"]:
                    result.update(state="conflict", candidate_id=None,
                                  notices=[notice("version_conflict", "Case inputs changed before public review submission; reconcile before another write.")])
                else:
                    query = build_query(snapshot, {"program_id":arguments["program_id"], "version":arguments["base_version"]}, now)
                    catalog = self._catalog_in(connection)
                    base = next((rule for rule in catalog["rules"] if rule["program_id"] == arguments["program_id"] and rule["version"] == arguments["base_version"]), None)
                    if query["issuing_state"] != "CO" or query["jurisdiction_state"] != "reported" or base is None:
                        raise InvalidInput("$.program_id", "Review submissions require a current published program version and explicit matching document issuer.")
                    record = candidate_from_fetch(identifier, kind, arguments, fetched, now)
                    connection.execute("INSERT INTO knowledge_candidates VALUES (?,?)", (identifier,canonical_json(record)))
                    connection.execute("INSERT INTO knowledge_effects VALUES (?,?,?,?)", (case_id,parent_event_id,effect_key,identifier))
                if time.monotonic() >= deadline:
                    raise service_error(409, "agent_run_inactive", "Late public review submissions were rolled back.")
                self._active_run(connection, case_id, parent_event_id, run_id, self.clock())
                validate("KnowledgeSubmissionResult", result)
                return result
        except sqlite3.Error:
            raise service_error(503, "knowledge_storage_unavailable", "Review storage is unavailable; no partial review submission was committed.", True) from None

    def read_review_queue(self, authority, limit=50):
        require_manual(authority)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvalidInput("$.limit", "Review queue limits are 1 to 100.")
        with self._connection() as connection:
            records = [json.loads(row["record_json"]) for row in connection.execute("SELECT record_json FROM knowledge_candidates ORDER BY candidate_id LIMIT ?", (limit,))]
            for record in records:
                validate("RuleReviewCandidate", record)
            return records

    def read_review_candidate(self, authority, candidate_id):
        require_manual(authority)
        validate("Id", candidate_id)
        with self._connection() as connection:
            row = connection.execute("SELECT record_json FROM knowledge_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
            if row is None:
                raise service_error(404, "candidate_unavailable", "The review candidate is unavailable.")
            record = json.loads(row["record_json"])
            validate("RuleReviewCandidate", record)
            return record

    def review_rule_candidate(self, authority, request):
        require_manual(authority)
        validate("ManualRuleReviewRequest", request)
        fingerprint = self._fingerprint([authority.reviewer, {k:v for k,v in request.items() if k not in ("expected_candidate_revision", "expected_catalog_version")}])
        try:
            with self._transaction() as connection:
                now = self.clock()
                prior = connection.execute("SELECT fingerprint,result_json FROM knowledge_reviews WHERE event_id=?", (request["event_id"],)).fetchone()
                if prior:
                    if prior["fingerprint"] != fingerprint:
                        raise service_error(400, "event_id_reused", "Changed manual review intent needs a new event ID.")
                    result = json.loads(prior["result_json"])
                    result["status"] = "already_applied"
                    return result
                row = connection.execute("SELECT record_json FROM knowledge_candidates WHERE candidate_id=?", (request["candidate_id"],)).fetchone()
                if row is None:
                    raise service_error(404, "candidate_unavailable", "The review candidate is unavailable.")
                candidate = json.loads(row["record_json"])
                validate("RuleReviewCandidate", candidate)
                catalog = self._catalog_in(connection)
                if (candidate["revision"] != request["expected_candidate_revision"] or catalog["version"] != request["expected_catalog_version"]
                        or candidate["review_state"] != "pending"):
                    raise service_error(409, "review_version_conflict", "Candidate/catalog changed; review the latest state before retrying.")
                decision, bundle = request["decision"], request["publication"]
                if (decision == "publish") != (bundle is not None) or decision == "resolve" and candidate["kind"] != "discrepancy":
                    raise InvalidInput("$.decision", "Only publication has a reviewed bundle; only discrepancies can be resolved.")
                published_version = None
                if decision == "publish":
                    base = next((rule for rule in catalog["rules"] if rule["program_id"] == candidate["program_id"] and rule["version"] == candidate["base_version"]), None)
                    if base is None:
                        raise service_error(409, "review_version_conflict", "The base program version is no longer active.")
                    validate_publication(bundle, candidate, base, now)
                    new_rule = bundle["rule"]
                    if connection.execute("SELECT 1 FROM knowledge_versions WHERE rule_id=? AND version=?", (new_rule["id"],new_rule["version"])).fetchone():
                        raise InvalidInput("$.publication.rule.version", "Published versions are immutable; choose a new version.")
                    old_bundle = {"rule":base, "sources":[source for source in catalog["sources"] if source["id"] in base["source_ids"]]}
                    connection.execute("INSERT OR IGNORE INTO knowledge_versions VALUES (?,?,?)", (base["id"],base["version"],canonical_json(old_bundle)))
                    connection.execute("INSERT INTO knowledge_versions VALUES (?,?,?)", (new_rule["id"],new_rule["version"],canonical_json(bundle)))
                    catalog["rules"] = [new_rule if rule["id"] == base["id"] else rule for rule in catalog["rules"]]
                    # Source IDs are shared by immutable records. Reject altering another
                    # active program's attribution; use a separately reviewed source ID.
                    retained_ids = {identifier for rule in catalog["rules"] if rule["id"] != new_rule["id"] for identifier in rule["source_ids"]}
                    old_sources = {source["id"]:source for source in catalog["sources"]}
                    for source in bundle["sources"]:
                        if source["id"] in retained_ids and old_sources.get(source["id"]) != source:
                            raise InvalidInput("$.publication.sources", "Publication cannot alter attribution used by another active program.")
                        old_sources[source["id"]] = source
                    ids = {identifier for rule in catalog["rules"] for identifier in rule["source_ids"]}
                    catalog["sources"] = [source for identifier,source in old_sources.items() if identifier in ids]
                    catalog["version"] = "review_" + self._fingerprint([request["event_id"],catalog])[:40]
                    validate_catalog(catalog)
                    connection.execute("INSERT INTO knowledge_catalog VALUES (1,?) ON CONFLICT(singleton) DO UPDATE SET catalog_json=excluded.catalog_json", (canonical_json(catalog),))
                    published_version = new_rule["version"]
                candidate["review_state"] = {"publish":"published", "reject":"rejected", "resolve":"resolved"}[decision]
                candidate["revision"] += 1
                validate("RuleReviewCandidate", candidate)
                connection.execute("UPDATE knowledge_candidates SET record_json=? WHERE candidate_id=?", (canonical_json(candidate),candidate["id"]))
                result = {"contract_version":VERSION, "event_id":request["event_id"], "status":"applied", "candidate_id":candidate["id"],
                          "review_state":candidate["review_state"], "candidate_revision":candidate["revision"],
                          "catalog_version":catalog["version"], "published_version":published_version}
                validate("ManualRuleReviewResult", result)
                connection.execute("INSERT INTO knowledge_reviews VALUES (?,?,?,?,?,?)", (request["event_id"],fingerprint,authority.reviewer,now,canonical_json(request),canonical_json(result)))
                return result
        except sqlite3.Error:
            raise service_error(503, "knowledge_storage_unavailable", "Manual review storage failed; catalog, candidate and review audit were rolled back together.", True) from None
