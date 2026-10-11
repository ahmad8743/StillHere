"""Read-only C04 requirements. Retrieval does not decide household eligibility or publish rules."""

import copy
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from ..contracts import InvalidInput, VERSION, validate
from ..incidents.geography import STATE_FIPS

RULES_PATH = Path(__file__).with_name("program_rules.json")
MAX_RULES = 4
REFERRAL_URL = "https://www.usa.gov/replace-vital-documents"


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_query(snapshot, arguments, now):
    validate("ProgramRuleToolArguments", arguments)
    fact = snapshot["facts"].get("document_issuing_state", {})
    state, jurisdiction_state = None, "unknown"
    reported_state = fact.get("state")
    if reported_state in ("conflicting", "stale"):
        jurisdiction_state = reported_state
    elif reported_state in ("user_reported", "source_supported") and fact.get("value") is not None:
        value = fact["value"]
        if isinstance(value, str) and value in STATE_FIPS:
            state, jurisdiction_state = value, "reported"
        else:
            jurisdiction_state = "invalid"
    query = {"program_id": arguments["program_id"], "requested_version": arguments.get("version"),
             "issuing_state": state, "jurisdiction_state": jurisdiction_state,
             "input_case_version": snapshot["case_version"], "as_of": now}
    _validate_query(query)
    return query


def _validate_query(query):
    validate("ProgramRuleQuery", query)
    if (query["jurisdiction_state"] == "reported") != (query["issuing_state"] is not None):
        raise InvalidInput("$.query.issuing_state", "A rule lookup requires a consistent reported issuing jurisdiction.")


def _url(value, hosts):
    try:
        parsed = urlsplit(value)
        safe = (parsed.scheme == "https" and parsed.hostname in hosts and not parsed.username
                and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        safe = False
    if not safe:
        raise InvalidInput("$.sources.url", "Rule sources and destinations must use approved official hosts.")


def _graph(path, source_ids):
    nodes = {node["id"]: node for node in path["nodes"]}
    if len(nodes) != len(path["nodes"]) or path["root_id"] not in nodes:
        raise InvalidInput("$.paths.nodes", "Requirement nodes must have unique IDs and a valid root.")
    for node in nodes.values():
        if not node["source_ids"] or not set(node["source_ids"]) <= source_ids:
            raise InvalidInput("$.paths.nodes.source_ids", "Each requirement must reference its rule's reviewed sources.")
        leaf = node["operator"] == "requirement"
        if (leaf and (node["children"] or node["requirement"] is None)
                or not leaf and (not node["children"] or node["requirement"] is not None)):
            raise InvalidInput("$.paths.nodes", "Leaves contain requirements; AND/OR groups contain child references.")
        if not set(node["children"]) <= set(nodes):
            raise InvalidInput("$.paths.nodes.children", "Every child must reference a node in its own path.")
    depths = {}
    def walk(identifier, ancestors):
        if identifier in ancestors:
            raise InvalidInput("$.paths.nodes", "Requirement graphs must be acyclic and at most eight levels deep.")
        if identifier in depths:
            return depths[identifier]
        depth = 1 + max((walk(child, ancestors | {identifier}) for child in nodes[identifier]["children"]), default=0)
        if depth > 8:
            raise InvalidInput("$.paths.nodes", "Requirement graphs must be acyclic and at most eight levels deep.")
        depths[identifier] = depth
        return depth
    walk(path["root_id"], set())
    if set(depths) != set(nodes):
        raise InvalidInput("$.paths.nodes", "Every requirement must be reachable from its path root.")


def validate_catalog(catalog):
    validate("PublishedProgramRuleCatalog", catalog)
    sources = {source["id"]: source for source in catalog["sources"]}
    if len(sources) != len(catalog["sources"]):
        raise InvalidInput("$.sources", "Rule source identities must be unique.")
    identities = {(rule["id"], rule["version"]) for rule in catalog["rules"]}
    if len(identities) != len(catalog["rules"]):
        raise InvalidInput("$.rules", "Published rule/version identities must be unique.")
    for source in sources.values():
        _url(source["url"], {"dmv.colorado.gov"})
        if not source["id"].startswith("source_rule_") or not source["supporting_sections"]:
            raise InvalidInput("$.sources", "Each rule source needs an isolated ID and supporting section.")
        if (_instant(source["expires_at"]) <= _instant(source["reviewed_at"])
                or _instant(source["retrieved_at"]) > _instant(source["reviewed_at"])):
            raise InvalidInput("$.sources", "Source review times must follow retrieval and precede expiry.")
    for rule in catalog["rules"]:
        ids = set(rule["source_ids"])
        if not ids or not ids <= set(sources) or not rule["paths"]:
            raise InvalidInput("$.rules", "Published rules need reviewed sources and at least one requirement path.")
        if len({path["id"] for path in rule["paths"]}) != len(rule["paths"]):
            raise InvalidInput("$.rules.paths", "Path identities must be unique within a rule.")
        if _instant(rule["review_expires_at"]) <= _instant(rule["reviewed_at"]):
            raise InvalidInput("$.rules.review_expires_at", "Rule review expiry must follow its review time.")
        if rule["effective_from"] and rule["effective_to"] and _instant(rule["effective_from"]) >= _instant(rule["effective_to"]):
            raise InvalidInput("$.rules.effective_to", "An effective interval must end after it begins.")
        for identifier in ids:
            source = sources[identifier]
            if source["jurisdiction"] != rule["jurisdiction"] or source["issuer"] != rule["issuer"]:
                raise InvalidInput("$.rules.source_ids", "Rule attribution must match the program issuer and jurisdiction.")
        for path in rule["paths"]:
            _url(path["official_url"], {"dmv.colorado.gov", "mydmv.colorado.gov"})
            _graph(path, ids)


def validate_result(result):
    validate("ProgramRuleResult", result)
    query = result["query"]
    _validate_query(query)
    validate_catalog({"version": result["catalog_version"] or "unavailable", "rules": result["rules"], "sources": result["sources"]})
    if {source["id"] for source in result["sources"]} != {identifier for rule in result["rules"] for identifier in rule["source_ids"]}:
        raise InvalidInput("$.sources", "Attribution must match the returned rule references.")
    for rule in result["rules"]:
        if (query["jurisdiction_state"] != "reported" or rule["jurisdiction"]["state"] != query["issuing_state"]
                or rule["program_id"] != query["program_id"]
                or query["requested_version"] is not None and rule["version"] != query["requested_version"]):
            raise InvalidInput("$.rules", "Returned rules must match the requested program, issuing state and version.")
    if result["state"] in ("no_match", "unknown", "unavailable", "conflict") and result["rules"]:
        raise InvalidInput("$.state", "Unresolved or failed lookups cannot claim applicable rules.")
    if result["state"] in ("available", "stale", "conflicting") and not result["rules"]:
        raise InvalidInput("$.state", "A retrieved result needs its reviewed rule records.")
    if result["state"] in ("available", "stale") and len(result["rules"]) != 1:
        raise InvalidInput("$.state", "A single resolved version is required for an available or stale result.")
    if result["state"] == "conflicting" and len(result["rules"]) < 2:
        raise InvalidInput("$.state", "Conflicting rules must retain multiple matching versions.")


def notice(code, message, retryable=False):
    return {"code": code, "message": message, "retryable": retryable}


class ProgramRuleStore:
    def __init__(self, loader=None, version_loader=None):
        self.loader = loader or self._load
        self.version_loader = version_loader

    @staticmethod
    def _load():
        def pairs(entries):
            result = {}
            for key, value in entries:
                if key in result:
                    raise ValueError("Duplicate public catalog field.")
                result[key] = value
            return result
        return json.loads(RULES_PATH.read_text(), object_pairs_hook=pairs)

    def lookup(self, query, deadline=None):
        _validate_query(query)
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Rule lookup deadline reached.")
        result = {"contract_version": VERSION, "query": copy.deepcopy(query), "catalog_version": None,
                  "state": "unknown", "rules": [], "sources": [], "household_eligibility": "unknown",
                  "referral_url": REFERRAL_URL, "notices": []}
        if query["jurisdiction_state"] != "reported":
            result["notices"] = [notice("rule_issuing_jurisdiction_unknown", "Report the document's issuing state before selecting rules. Current or damaged location cannot establish its issuer.")]
            validate_result(result)
            return result
        try:
            catalog = self.loader()
            validate_catalog(catalog)
            if (query["requested_version"] is not None and self.version_loader is not None
                    and not any(rule["program_id"] == query["program_id"] and rule["version"] == query["requested_version"] for rule in catalog["rules"])):
                catalog = self.version_loader(query["requested_version"])
                validate_catalog(catalog)
        except (OSError, ValueError, TypeError, RecursionError):
            result["state"] = "unavailable"
            result["notices"] = [notice("rule_store_unavailable", "Reviewed program rules could not be read or validated. This is not a no-match result; use the official referral.", True)]
            validate_result(result)
            return result
        result["catalog_version"] = catalog["version"]
        selected = [copy.deepcopy(rule) for rule in catalog["rules"] if rule["program_id"] == query["program_id"]
                    and rule["jurisdiction"]["state"] == query["issuing_state"]
                    and (query["requested_version"] is None or rule["version"] == query["requested_version"])]
        truncated = len(selected) > MAX_RULES
        result["rules"] = selected[:MAX_RULES]
        ids = {identifier for rule in result["rules"] for identifier in rule["source_ids"]}
        now = _instant(query["as_of"])
        sources = [copy.deepcopy(source) for source in catalog["sources"] if source["id"] in ids]
        for source in sources:
            source["freshness"] = "current" if _instant(source["reviewed_at"]) <= now < _instant(source["expires_at"]) else "stale"
        result["sources"] = sources
        stale = (any(source["freshness"] == "stale" for source in sources)
                 or any(not _instant(rule["reviewed_at"]) <= now < _instant(rule["review_expires_at"])
                        or rule["effective_from"] is not None and now < _instant(rule["effective_from"])
                        or rule["effective_to"] is not None and now >= _instant(rule["effective_to"]) for rule in selected))
        result["state"] = "conflicting" if len(selected) > 1 else "stale" if selected and stale else "available" if selected else "no_match"
        result["notices"] = [notice("rule_partial_requirements", "These seeded reviewed reference paths are partial. Fees, proof alternatives and full eligibility remain unresolved. Requirement evidence states stay unknown; no application, publication or case mutation occurs."),
                             notice("rule_bounded_coverage", "Only the selected program, issuing jurisdiction and version are covered. No match does not rule out other recovery routes.")]
        if any(rule["effective_from"] is None or rule["effective_to"] is None for rule in selected):
            result["notices"].append(notice("rule_effective_dates_unknown", "Review times do not establish policy effective dates. Unstated effective boundaries remain unknown."))
        if len(selected) > 1:
            result["notices"].append(notice("rule_versions_conflicting", "More than one published rule version matches. Keep the alternatives visible; do not silently choose the newest. Specify a reviewed version or resolve the discrepancy."))
        if stale:
            result["notices"].append(notice("rule_review_stale", "One or more source/rule reviews expired or the effective interval does not cover this lookup. Retained rules require confirmation before use."))
        if truncated:
            result["notices"].append(notice("rule_results_truncated", "At most four matching rule versions are returned; the result does not establish complete coverage."))
        validate_result(result)
        return result
