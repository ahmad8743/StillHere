"""Evaluate bounded published AND/OR graphs without inferring policy or writing a plan."""

import copy
import hashlib

from ..contracts import InvalidInput, VERSION, validate
from ..knowledge.rules import _instant, build_query, notice, validate_result


def _combine(operator, states):
    if operator == "all_of":
        return "unmet" if "unmet" in states else "unknown" if "unknown" in states else "satisfied"
    return "satisfied" if "satisfied" in states else "unknown" if "unknown" in states else "unmet"


def _answer(snapshot, requirement, source_ids, as_of):
    """Only exact Boolean reports count; confirmation has a stronger provenance gate."""
    fact = snapshot["facts"].get(requirement["key"])
    if fact is None:
        return "unknown", "missing", None, "fact_missing"
    state, observed = fact["state"], fact["observed_at"]
    if state not in ("user_reported", "source_supported"):
        return "unknown", state, observed, "fact_" + state
    if type(fact["value"]) is not bool:
        return "unknown", state, observed, "fact_invalid"
    if observed is None or _instant(observed) > _instant(as_of):
        return "unknown", state, observed, "observation_unusable"
    if requirement["kind"] == "authority_confirmation" and (
            state != "source_supported" or not set(fact["source_ids"]) & set(source_ids)):
        return "unknown", state, observed, "authority_unverified"
    matched = fact["value"] is requirement["expected"]
    return ("satisfied" if matched else "unmet"), state, observed, ("reported_match" if matched else "reported_mismatch")


def _path(snapshot, rule, path, rule_state, as_of):
    nodes = {node["id"]: node for node in path["nodes"]}
    evaluated, frontiers = {}, {}

    def walk(identifier):
        if identifier in evaluated:
            return evaluated[identifier]["state"]
        node = nodes[identifier]
        requirement = node["requirement"]
        if requirement:
            state, fact_state, observed, reason = _answer(snapshot, requirement, node["source_ids"], as_of)
            blockers = {identifier} if state == "unmet" else set()
            questions = {identifier} if state == "unknown" else set()
        else:
            states = [walk(child) for child in node["children"]]
            state = _combine(node["operator"], states)
            fact_state, observed, reason = None, None, "and_or_evaluation"
            active = node["children"]
            if node["operator"] == "any_of":
                # A failed optional branch cannot block a satisfied OR. For an
                # unresolved OR, only unresolved branches are necessary questions.
                active = [] if state == "satisfied" else [child for child in active if evaluated[child]["state"] == state]
            blockers = set().union(*(frontiers[child][0] for child in active))
            questions = set().union(*(frontiers[child][1] for child in active))
        evaluated[identifier] = {"node_id": identifier, "operator": node["operator"],
                                 "children": list(node["children"]), "requirement": copy.deepcopy(requirement),
                                 "state": state, "fact_state": fact_state, "observed_at": observed,
                                 "reason": reason, "source_ids": list(node["source_ids"])}
        frontiers[identifier] = blockers, questions
        return state

    root_state = walk(path["root_id"])
    blocker_ids, question_ids = (set(items) for items in frontiers[path["root_id"]])
    # These are household access checks, not additions to published DMV policy.
    access_key, access_label = None, None
    if path["execution_mode"] == "in_person":
        access_key, access_label = "office_transport_available", "A way to reach the office is available"
    elif path["execution_mode"] == "online":
        access_key, access_label = "internet_access", "Internet access for the online route is available"
    constraints = []
    if access_key:
        requirement = {"key": access_key, "kind": "fact", "label": access_label,
                       "expected": True, "timing": "before_start", "evidence_state": "unknown"}
        state, fact_state, observed, reason = _answer(snapshot, requirement, [], as_of)
        mobility = snapshot["facts"].get("mobility", {})
        if (access_key == "office_transport_available" and state == "unknown"
                and mobility.get("state") in ("user_reported", "source_supported")
                and mobility.get("value") == "no_car" and mobility.get("observed_at") is not None
                and _instant(mobility["observed_at"]) <= _instant(as_of)):
            reason = "no_car_transport_unknown"
        identifier = "constraint_" + access_key
        while identifier in evaluated:
            identifier += "_"
        access = {"node_id": identifier, "operator": "requirement", "children": [],
                  "requirement": requirement, "state": state, "fact_state": fact_state,
                  "observed_at": observed, "reason": reason, "source_ids": []}
        evaluated[identifier] = access
        constraints.append(access)
        if state == "unmet":
            blocker_ids.add(identifier)
        elif state == "unknown":
            question_ids.add(identifier)
        root_state = _combine("all_of", [root_state, state])

    blockers = [{"node_id": identifier, "fact_key": evaluated[identifier]["requirement"]["key"],
                 "code": "requirement_unmet", "message": evaluated[identifier]["requirement"]["label"],
                 "source_ids": evaluated[identifier]["source_ids"]} for identifier in sorted(blocker_ids)]
    questions = []
    for identifier in sorted(question_ids):
        item = evaluated[identifier]
        text = "Is this requirement met: " + item["requirement"]["label"] + "? Report only availability/completion, not document numbers or contents."
        if item["reason"] == "authority_unverified" or item["requirement"]["kind"] == "authority_confirmation":
            text = "Obtain issuing-agency confirmation of: " + item["requirement"]["label"] + ". A household report alone does not verify agency eligibility or applicability."
        if item["reason"] == "no_car_transport_unknown":
            text = "You reported no car. Is another way to reach the office available? Transport availability and cost remain unknown."
        questions.append({"node_id": identifier, "fact_key": item["requirement"]["key"],
                          "code": item["reason"], "message": text, "source_ids": item["source_ids"]})
    # Incomplete published coverage is never upgraded by a set of matching answers.
    if not rule["coverage_complete"]:
        questions.append({"node_id": None, "fact_key": None, "code": "policy_coverage_partial",
                          "message": "Confirm the full applicable requirements with the issuing agency; this published reference is partial.",
                          "source_ids": list(rule["source_ids"])})
    for text in path["unresolved_requirements"]:
        questions.append({"node_id": None, "fact_key": None, "code": "policy_requirement_unresolved",
                          "message": text, "source_ids": list(rule["source_ids"])})
    questions.append({"node_id": None, "fact_key": None, "code": "costs_unknown",
                      "message": "Confirm the current fee, any transport cost and their dates. Unknown costs are not zero or confirmed savings.",
                      "source_ids": list(rule["source_ids"])})
    alternatives = []
    for node in path["nodes"]:
        if node["operator"] == "any_of":
            alternatives.append({"group_node_id": node["id"], "source_ids": list(node["source_ids"]),
                                 "branches": [{"node_id": child, "state": evaluated[child]["state"],
                                               "blocker_node_ids": sorted(frontiers[child][0]),
                                               "question_node_ids": sorted(frontiers[child][1])} for child in node["children"]]})
    identity = hashlib.sha256(f"{rule['id']}\0{rule['version']}\0{path['id']}".encode()).hexdigest()[:32]
    status = "blocked" if root_state == "unmet" else "feasible" if (
        root_state == "satisfied" and rule_state == "available" and rule["coverage_complete"]
        and not path["unresolved_requirements"]) else "provisional"
    return {"id": "option_" + identity, "rule_id": rule["id"], "rule_version": rule["version"],
            "path_id": path["id"], "title": path["title"], "execution_mode": path["execution_mode"],
            "official_url": path["official_url"], "root_id": path["root_id"], "status": status,
            "requirement_state": root_state, "requirements": [evaluated[node["id"]] for node in path["nodes"]],
            "constraints": constraints, "blockers": blockers, "questions": questions,
            "alternatives": alternatives, "alternative_option_ids": [], "source_ids": list(rule["source_ids"]),
            "limitations": list(rule["limitations"]),
            "costs": {"state": "unknown", "fee_cents": path["fee_cents"], "transport_cents": None,
                      "cost_date": None, "source_ids": list(rule["source_ids"])}}


def evaluate_options(snapshot, rules):
    """Pure, deterministic result for one exact case version and public rule query.

    Graph shape/reachability/depth/cycles are validated before any evaluation.
    Untyped snapshot evidence/tasks are deliberately not interpreted in this slice.
    """
    validate("CaseSnapshot", snapshot)
    validate_result(rules)
    query = rules["query"]
    arguments = {"program_id": query["program_id"]}
    if query["requested_version"] is not None:
        arguments["version"] = query["requested_version"]
    if query != build_query(snapshot, arguments, query["as_of"]):
        raise InvalidInput("$.query", "Planner rules must match the exact case version and reported document issuer.")
    result = {"contract_version": VERSION, "state": rules["state"], "query": copy.deepcopy(query),
              "catalog_version": rules["catalog_version"], "options": [], "blockers": [], "questions": [],
              "sources": copy.deepcopy(rules["sources"]), "household_eligibility": "unknown",
              "referral_url": rules["referral_url"], "notices": copy.deepcopy(rules["notices"])}
    if rules["state"] in ("available", "stale", "conflicting"):
        for rule in rules["rules"]:
            for path in rule["paths"]:
                result["options"].append(_path(snapshot, rule, path, rules["state"], query["as_of"]))
        for option in result["options"]:
            option["alternative_option_ids"] = [other["id"] for other in result["options"]
                                                if other["id"] != option["id"] and other["rule_id"] == option["rule_id"]
                                                and other["rule_version"] == option["rule_version"]]
    if rules["state"] != "available":
        result["blockers"].append({"node_id": None, "fact_key": None, "code": "rules_" + rules["state"],
                                   "message": "The rule lookup is " + rules["state"] + "; resolve its notices before relying on these options.", "source_ids": []})
        if rules["state"] in ("unknown", "stale", "conflicting"):
            result["questions"].append({"node_id": None, "fact_key": "document_issuing_state" if rules["state"] == "unknown" else None,
                                        "code": "rules_" + rules["state"], "message": "Report the document's issuing state." if rules["state"] == "unknown" else "Confirm a current, unambiguous published rule version with the issuing agency.", "source_ids": []})
    result["notices"].append(notice("planner_read_only", "This evaluates explicit Boolean availability/completion facts and household access constraints. It does not verify eligibility, costs, documents, task history or agency decisions, revise a saved plan or change any case domain."))
    validate("RecoveryOptionResult", result)
    return result
