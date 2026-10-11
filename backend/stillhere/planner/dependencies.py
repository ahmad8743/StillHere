"""Typed, version-pinned prerequisite evaluation; no durable writes or eligibility claims."""

import copy

from .evaluator import _combine
from .plans import ORIGIN, TERMINAL
from .validation import (actions, check, current, fail, instant, owned, records,
                         scope_matches, supported, usable)


def _graph(action):
    nodes = {node["node_id"]: node for node in action["requirements"]}
    if not nodes or len(nodes) != len(action["requirements"]):
        fail("$.requirements", "Expected unique nodes in a nonempty graph.")
    children = {child for node in nodes.values() for child in node["children"]}
    roots = set(nodes) - children
    if len(roots) != 1 or children - set(nodes):
        fail("$.requirements", "Expected one graph root and valid child references.")
    visited, heights = set(), {}

    def walk(identifier, path):
        if identifier in path or len(path) >= 8:
            fail("$.requirements", "Requirement graphs must be acyclic with at most eight levels.")
        if identifier in heights:
            if len(path) + heights[identifier] > 8:
                fail("$.requirements", "Requirement graphs support at most eight levels.")
            return heights[identifier]
        node = nodes[identifier]
        if node["operator"] == "requirement":
            if node["requirement"] is None or node["children"]:
                fail("$.requirements", "Requirement leaves must have a predicate and no children.")
        elif node["requirement"] is not None or not node["children"] or len(set(node["children"])) != len(node["children"]):
            fail("$.requirements", "AND/OR groups must have unique nonempty children and no predicate.")
        visited.add(identifier)
        height = 1 + max((walk(child, path | {identifier}) for child in node["children"]), default=0)
        heights[identifier] = height
        return height

    root = next(iter(roots))
    walk(root, set())
    if visited != set(nodes):
        fail("$.requirements", "Every requirement must be reachable from the root.")
    return nodes, root


def _cycles(mapping, links):
    """Bounded SCC discovery via reachability (at most 32 actions, 128 links)."""
    edges = {identifier: set() for identifier in mapping}
    for link in links:
        if link["kind"] == "action":
            source, target = mapping[link["action_id"]], mapping.get(link["target_id"])
            if (source["status"] not in TERMINAL and current(source) and target and
                    target.get("origin") == ORIGIN and target["status"] not in TERMINAL and current(target) and
                    target["rule_id"] == link["target_rule_id"] and
                    target["rule_version"] == link["target_rule_version"]):
                edges[source["id"]].add(target["id"])

    def reachable(start):
        seen, todo = set(), list(edges[start])
        while todo:
            node = todo.pop()
            if node not in seen:
                seen.add(node)
                todo.extend(edges[node])
        return seen

    reach = {node: reachable(node) for node in edges}
    groups, assigned = [], set()
    for node in sorted(edges):
        if node in assigned or node not in reach[node]:
            continue
        group = {other for other in reach[node] if node in reach[other]} | {node}
        assigned |= group
        groups.append({"code": "dependency_cycle", "action_ids": sorted(group),
                       "link_ids": sorted(link["id"] for link in links if link["kind"] == "action"
                                          and link["action_id"] in group and link["target_id"] in group)})
    return groups


def _diagnostic(node, code):
    return {"node_id": node["node_id"], "fact_key": node["requirement"]["key"],
            "code": code, "message": "Resolve this typed prerequisite: " + node["requirement"]["label"] + ".",
            "source_ids": list(node["source_ids"])}


def resolve_dependencies(plan, *, case_id, input_case_version, links, evidence, confirmations, as_of):
    """Return a proposed plan evaluated against backend-selected, case-scoped records.

    Explicit links override only their typed predicate. Unlinked predicates keep
    the existing fact evaluation. Terminal records are never rewritten. Supplied
    confirmations must already be authorized/attributed by CaseService; these
    ordinary-data records cannot grant that authority to a caller.
    """
    check("Id", case_id)
    if type(input_case_version) is not int or input_case_version < 1:
        fail("$.input_case_version", "Expected a positive case version.")
    query_time = instant(as_of)
    mapping = actions(plan)
    if any(a.get("origin") == ORIGIN and a["input_case_version"] > input_case_version for a in mapping.values()):
        fail("$.input_case_version", "Planner inputs cannot come from a later case version.")
    link_map = records("PlannerDependencyLink", links)
    evidence_map = records("PlannerEvidence", evidence)
    confirmation_map = records("PlannerConfirmation", confirmations)
    if any(record["case_id"] != case_id for record in list(evidence_map.values()) + list(confirmation_map.values())):
        fail("$.case_id", "Evidence and confirmations must belong to this authorized case.")
    graphs = {identifier: _graph(action) for identifier, action in mapping.items() if action.get("origin") == ORIGIN}
    by_node = {}
    for link in link_map.values():
        consumer = owned(mapping, link["action_id"])
        node = graphs[consumer["id"]][0].get(link["node_id"])
        if not scope_matches(link, consumer) or node is None or node["requirement"] is None:
            fail("$.links", "Link must identify a leaf in the consumer's exact rule version.")
        kind = {"evidence": "evidence", "action": "action", "confirmation": "authority_confirmation"}[link["kind"]]
        if node["requirement"]["kind"] != kind:
            fail("$.links.kind", "Link type must match the published requirement kind.")
        if link["kind"] == "action":
            if link["target_rule_id"] is None or link["target_rule_version"] is None:
                fail("$.links", "Action dependencies must pin the target rule version.")
        elif link["target_rule_id"] is not None or link["target_rule_version"] is not None:
            fail("$.links", "Only action links carry a target rule version.")
        key = (consumer["id"], node["node_id"])
        if key in by_node:
            fail("$.links", "One typed link per leaf; represent alternatives with published OR nodes.")
        by_node[key] = link
    if any(sum(link["action_id"] == identifier for link in links) > 32 for identifier in mapping):
        fail("$.links", "At most 32 links per action are supported.")
    cycles = _cycles(mapping, links)
    cyclic_links = {identifier for cycle in cycles for identifier in cycle["link_ids"]}
    result = copy.deepcopy(plan)
    out = {action["id"]: action for action in result["actions"]}
    for identifier in sorted(graphs):
        action = out[identifier]
        if action["status"] in TERMINAL:
            continue
        action["dependency_links"] = sorted((copy.deepcopy(link) for link in links if link["action_id"] == identifier), key=lambda link: link["id"])
        if not current(action):
            continue
        nodes, root = _graph(action)
        memo, frontiers = {}, {}

        def answer(node):
            link = by_node.get((identifier, node["node_id"]))
            if link is None:
                return node["state"], node["reason"], node["fact_state"], node["observed_at"]
            expected = node["requirement"]["expected"]
            if link["kind"] == "action":
                target = mapping.get(link["target_id"])
                if link["id"] in cyclic_links:
                    return "unmet", "dependency_cycle", None, None
                if not target or target.get("origin") != ORIGIN or target["rule_id"] != link["target_rule_id"] or target["rule_version"] != link["target_rule_version"]:
                    return "unknown", "dependency_scope_unresolved", None, None
                if target["status"] != "completed" and not current(target):
                    return "unknown", "dependency_stale", None, None
                value = target["status"] == "completed"
                if value:
                    report = target["history"][-1] if target["history"] else None
                    if (report is None or report["status"] != "completed" or
                            instant(report["occurred_at"]) > query_time or instant(report["received_at"]) > query_time):
                        return "unknown", "dependency_completion_unverified", None, None
                reason = "dependency_completed" if value else "dependency_skipped" if target["status"] == "skipped" else "dependency_unfinished"
                return "satisfied" if value is expected else "unmet", reason, "user_reported" if target["status"] in TERMINAL else None, None
            record = (evidence_map if link["kind"] == "evidence" else confirmation_map).get(link["target_id"])
            reason = "evidence_unusable" if link["kind"] == "evidence" else "confirmation_unverified"
            if record is None or not usable(record, query_time):
                return "unknown", reason, record["state"] if record else "missing", record["observed_at"] if record else None
            if link["kind"] == "evidence":
                valid = record["key"] == node["requirement"]["key"]
                value = record["available"]
                if record["state"] == "source_supported":
                    valid = valid and supported(record, action, node, query_time)
            else:
                valid = (scope_matches(record, action) and record["action_id"] == identifier and
                         record["node_id"] == node["node_id"] and supported(record, action, node, query_time))
                value = record["value"]
            if not valid or value is None:
                return "unknown", reason, record["state"], record["observed_at"]
            matched = value is expected
            return ("satisfied" if matched else "unmet", ("evidence_" if link["kind"] == "evidence" else "confirmation_") + ("match" if matched else "mismatch"), record["state"], record["observed_at"])

        def walk(node_id):
            if node_id in memo:
                return memo[node_id]
            node = nodes[node_id]
            if node["operator"] == "requirement":
                state, reason, fact_state, observed = answer(node)
                node.update(state=state, reason=reason, fact_state=fact_state, observed_at=observed)
                blockers = {node_id} if state == "unmet" else set()
                questions = {node_id} if state == "unknown" else set()
            else:
                state = _combine(node["operator"], [walk(child) for child in node["children"]])
                active = node["children"]
                if node["operator"] == "any_of":
                    active = [] if state == "satisfied" else [child for child in active if memo[child] == state]
                blockers = set().union(*(frontiers[child][0] for child in active))
                questions = set().union(*(frontiers[child][1] for child in active))
                node.update(state=state, reason="and_or_evaluation")
            memo[node_id] = state
            frontiers[node_id] = blockers, questions
            return state

        root_state = walk(root)
        # Retain access/report/partial-policy diagnostics; rebuild graph diagnostics.
        for field in ("blockers", "questions"):
            action[field] = [item for item in action[field] if item.get("node_id") not in nodes]
        blocked, unknown = frontiers[root]
        action["blockers"] += [_diagnostic(nodes[node], nodes[node]["reason"]) for node in sorted(blocked)]
        action["questions"] += [_diagnostic(nodes[node], nodes[node]["reason"]) for node in sorted(unknown)]
        total_state = _combine("all_of", [root_state] + [node["state"] for node in action["constraints"]])
        # Never promote partial policy to an eligibility/feasibility decision.
        action["status"] = "blocked" if total_state == "unmet" or action["blockers"] else "waiting"
        action["reason"] = "Typed prerequisites reassessed; policy coverage and household eligibility remain provisional."
    result["dependency_cycles"] = cycles
    result["dependency_as_of"] = as_of
    result["dependency_input_case_version"] = input_case_version
    result["household_eligibility"] = "unknown"
    result["state"] = "pending" if plan.get("state") == "pending" or any(
        a.get("origin") == ORIGIN and a["status"] not in TERMINAL and not current(a) for a in out.values()) else "provisional"
    for field in ("blockers", "questions"):
        result[field] = [item for item in plan.get(field, []) if not item.get("action_id")]
        result[field] += [{**copy.deepcopy(item), "action_id": a["id"]} for a in out.values()
                          if a.get("origin") == ORIGIN and a["status"] not in TERMINAL for item in a[field]]
    # Cycles remain explicit even when an OR's independent branch is satisfied.
    result["blockers"] += [{"node_id": None, "fact_key": None, "code": "dependency_cycle",
                            "message": "Cross-action prerequisite cycle requires a supported alternative or link correction.",
                            "source_ids": [], "action_ids": cycle["action_ids"], "link_ids": cycle["link_ids"]} for cycle in cycles]
    actions(result)
    return result


def order_actions(plan, *, priorities=None, deadlines=None):
    """Pure proposed order: prerequisites first, then priority, deadline and ID.

    Historical terminal actions retain their relative order at the end. Cycles
    remain blocked diagnostics; their deterministic residual order is no promise
    of an executable sequence. Null deadlines sort after dated ties.
    """
    actions(plan)
    result = copy.deepcopy(plan)
    out = {a["id"]: a for a in result["actions"]}
    for record in records("PlannerPriority", priorities or [], 32, "action_id").values():
        action = owned(out, record["action_id"])
        if action["status"] in TERMINAL:
            fail("$.priorities", "Historical completed/skipped work is preserved.")
        action["priority"] = record["priority"]
    for record in records("PlannerDeadline", deadlines or [], 32, "action_id").values():
        action = owned(out, record["action_id"])
        if action["status"] in TERMINAL:
            fail("$.deadlines", "Historical completed/skipped work is preserved.")
        action["deadline"] = record["deadline"]
    active = {identifier for identifier, a in out.items() if a.get("origin") == ORIGIN and a["status"] not in TERMINAL}
    prerequisites = {identifier: {link["target_id"] for link in out[identifier].get("dependency_links", [])
                                  if link["kind"] == "action" and link["target_id"] in active and
                                  out[link["target_id"]]["rule_id"] == link["target_rule_id"] and
                                  out[link["target_id"]]["rule_version"] == link["target_rule_version"]}
                     for identifier in active}
    ordered = []

    def key(identifier):
        action = out[identifier]
        return action.get("priority", 100), action["deadline"] or "9999-12-31", identifier

    while active:
        ready = [identifier for identifier in active if not prerequisites[identifier] & active]
        if not ready:
            ordered.extend(sorted(active, key=key))
            break
        chosen = min(ready, key=key)
        ordered.append(chosen)
        active.remove(chosen)
    result["actions"] = [out[identifier] for identifier in ordered] + [out[a["id"]] for a in plan["actions"] if a["id"] not in ordered]
    actions(result)
    return result
