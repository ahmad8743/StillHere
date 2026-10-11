"""Dated nullable action costs and a finance proposal; never reads or writes a ledger."""

import copy
import hashlib
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .plans import ORIGIN, TERMINAL
from ..contracts import canonical_json
from .validation import (actions, check, current, fail, instant, owned, records,
                         scope_matches, supported)


def set_action_costs(plan, updates, *, as_of):
    """Attach explicit scoped cost records to active actions, preserving historical work."""
    query_time = instant(as_of)
    result = copy.deepcopy(plan)
    mapping = actions(result)
    for update in records("PlannerCostUpdate", updates, 32, "action_id").values():
        action = owned(mapping, update["action_id"])
        if not scope_matches(update, action) or not current(action):
            fail("$.costs", "Cost updates require the current action's exact rule version.")
        if action["status"] in TERMINAL:
            fail("$.costs", "Historical completed/skipped costs are preserved; correct them through finance audit.")
        if not update["items"]:
            fail("$.costs", "Explicit costs are required; an empty list cannot establish zero cost.")
        records("PlannerCostItem", update["items"], 16)
        for item in update["items"]:
            if item["observed_at"] is not None and instant(item["observed_at"]) > query_time:
                fail("$.costs.observed_at", "Cost observations cannot be in the future.")
        action["cost_items"] = copy.deepcopy(sorted(update["items"], key=lambda item: item["id"]))
    actions(result)
    return result


def _commitment_id(action_id, cost_id):
    return "planner_cost_" + hashlib.sha256((action_id + "\0" + cost_id).encode()).hexdigest()[:32]


def export_action_costs(plan, *, input_case_version, as_of, time_zone):
    """Return plain data for all paths. Only selected current paths become commitments.

    Missing dates/amounts remain null. Invalid source provenance and stale amounts
    become null usable amounts while their original records remain in cost_items.
    This is not a finance forecast and does not imply that paths are selected.
    """
    mapping = actions(plan)
    if type(input_case_version) is not int or input_case_version < 1:
        fail("$.input_case_version", "Expected a positive case version.")
    if any(a.get("origin") == ORIGIN and a["input_case_version"] > input_case_version for a in mapping.values()):
        fail("$.input_case_version", "Cost inputs cannot come from a later case version.")
    query_time = instant(as_of)
    try:
        zone = ZoneInfo(time_zone)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        fail("$.time_zone", "Use a valid case IANA time zone.")
    result = {"contract_version": "0.1", "input_case_version": input_case_version,
              "plan_version": plan["version"], "as_of": as_of, "time_zone": time_zone,
              "currency": "USD", "paths": []}
    for identifier in sorted(mapping):
        action = mapping[identifier]
        if action.get("origin") != ORIGIN:
            continue
        items = copy.deepcopy(action.get("cost_items", [
            {"id": category, "category": category, "amount_cents": action["costs"][key],
             "date": action["costs"]["cost_date"], "due_at": None, "state": "unknown",
             "observed_at": None, "source_ids": list(action["costs"]["source_ids"]), "essential": False}
            for category, key in (("fee", "fee_cents"), ("transport", "transport_cents"))]))
        records("PlannerCostItem", items, 16)
        if not items:
            fail("$.cost_items", "An empty cost list cannot establish zero cost.")
        warnings, commitments = set(), []
        selectable = current(action) and action["status"] in ("ready", "waiting") and not action["blockers"]
        if not current(action):
            warnings.add("action_inputs_stale")
        if action["status"] == "waiting":
            warnings.add("provisional_action")
        for item in sorted(items, key=lambda item: item["id"]):
            amount = item["amount_cents"]
            usable = (current(action) and item["state"] in ("user_reported", "source_supported") and
                      item["observed_at"] is not None and instant(item["observed_at"]) <= query_time)
            if item["state"] == "source_supported":
                usable = usable and supported(item, action, {"source_ids": action["source_ids"]}, query_time)
            if not usable:
                amount = None
                warnings.add("cost_unverified")
            if amount is None:
                warnings.add("cost_amount_unknown")
            if item["date"] is None:
                warnings.add("cost_date_unknown")
            if item["due_at"] is not None and item["date"] is not None and instant(item["due_at"]).astimezone(zone).date().isoformat() != item["date"]:
                fail("$.costs.due_at", "Cost time must match its date in the case time zone.")
            if action["status"] not in TERMINAL:
                commitments.append({"id": _commitment_id(identifier, item["id"]), "action_id": identifier,
                                    "planner_cost_id": item["id"], "category": item["category"],
                                    "amount_cents": amount, "date": item["date"], "due_at": item["due_at"],
                                    "essential": item["essential"], "priority": action.get("priority", 100),
                                    "source_ids": list(item["source_ids"])})
        result["paths"].append({"action_id": identifier, "rule_id": action["rule_id"], "rule_version": action["rule_version"],
                                "status": action["status"], "is_current": action["is_current"],
                                "input_freshness": action["input_freshness"], "alternative_ids": list(action["alternative_ids"]),
                                "selectable": selectable, "cost_state": "incomplete" if warnings - {"provisional_action"} else "known",
                                "cost_items": items, "commitments": commitments, "warnings": sorted(warnings)})
    check("PlannerCostExport", result)
    return result


def propose_alternative_selection(cost_export, selected_action_ids, *, existing_commitments):
    """Propose hypothetical replacement of explicitly planner-owned future costs.

    Ordinary essential commitments, actual/fulfilled costs, terminal work and
    unrelated records are retained. The consumer must validate the ledger and
    explicitly reconcile existing commitments before a CaseService commit.
    """
    check("PlannerCostExport", cost_export)
    query_time = instant(cost_export["as_of"])
    try:
        today = query_time.astimezone(ZoneInfo(cost_export["time_zone"])).date().isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        fail("$.time_zone", "Use a valid case IANA time zone.")
    if not isinstance(selected_action_ids, list) or len(selected_action_ids) > 32:
        fail("$.selected_action_ids", "Expected at most 32 action IDs.")
    for identifier in selected_action_ids:
        check("Id", identifier)
    if len(set(selected_action_ids)) != len(selected_action_ids):
        fail("$.selected_action_ids", "Selected action IDs must be unique.")
    paths = {path["action_id"]: path for path in cost_export["paths"]}
    if len(paths) != len(cost_export["paths"]):
        fail("$.paths", "Exported action identities must be unique.")
    if not isinstance(existing_commitments, list) or len(existing_commitments) > 256:
        fail("$.existing_commitments", "Expected a bounded list of synthetic finance commitments.")
    try:
        canonical_json(existing_commitments)
    except (TypeError, ValueError, RecursionError):
        fail("$.existing_commitments", "Commitments must contain finite JSON values.")
    existing = {}
    for record in existing_commitments:
        if not isinstance(record, dict):
            fail("$.existing_commitments", "Expected commitment records.")
        check("Id", record.get("id"))
        if record["id"] in existing:
            fail("$.existing_commitments", "Commitment identities must be unique.")
        existing[record["id"]] = record
    selected = set(selected_action_ids)
    issues = set()
    for identifier in selected:
        if identifier not in paths:
            fail("$.selected_action_ids", "Select an exported path from this case.")
        path = paths[identifier]
        if not path["selectable"]:
            issues.add("action_not_selectable")
        if any(other in selected for other in path["alternative_ids"]):
            issues.add("mutually_exclusive_alternatives")
        if path["cost_state"] == "incomplete":
            issues.add("costs_incomplete")
        if any((c["date"] is not None and c["date"] < today) or
               (c["due_at"] is not None and instant(c["due_at"]) < query_time)
               for c in path["commitments"]):
            issues.add("cost_timing_requires_reassessment")
        if "provisional_action" in path["warnings"]:
            issues.add("eligibility_and_policy_provisional")
    affected = set(selected)
    for identifier in selected:
        path = paths[identifier]
        # Only current same-rule/version siblings can be replaced implicitly.
        affected |= {other for other in path["alternative_ids"] if other in paths and
                     identifier in paths[other]["alternative_ids"] and
                     paths[other]["rule_id"] == path["rule_id"] and
                     paths[other]["rule_version"] == path["rule_version"]}
    removable, additions, retained = [], [], []
    for identifier, record in sorted(existing.items()):
        # Removal requires explicit ownership + matching stable action/cost IDs.
        path = paths.get(record.get("action_id"))
        cost_id = record.get("planner_cost_id")
        owned_cost = (record.get("origin") == "recovery_planner" and path is not None and
                      isinstance(cost_id, str) and identifier == _commitment_id(path["action_id"], cost_id))
        if not owned_cost or record.get("action_id") not in affected or path["status"] in TERMINAL:
            retained.append(identifier)
            continue
        if record.get("essential") is not False:
            retained.append(identifier)
            issues.add("essential_action_commitment_requires_review")
            continue
        # Require explicit, normalized zero fulfillment. Unknown/partial actual
        # spending and any actual-event link remain a finance reconciliation gate.
        untouched = (type(record.get("fulfilled_cents")) is int and record["fulfilled_cents"] == 0 and
                     record.get("actual_event_ids") == [])
        record_date = record.get("date")
        dated = isinstance(record_date, str)
        if dated:
            check("PlannerDate", record_date)
        future_cost = dated and record_date >= today
        if not future_cost or not untouched or not path["is_current"] or path["input_freshness"] != "current":
            retained.append(identifier)
            issues.add("commitment_reconciliation_required")
        else:
            removable.append(identifier)
    for identifier in sorted(selected):
        for commitment in paths[identifier]["commitments"]:
            if commitment["id"] in retained:
                issues.add("commitment_reconciliation_required")
            else:
                additions.append(copy.deepcopy(commitment))
    # A clarification proposal exposes a preview, but never a partial executable patch.
    blocked = issues - {"eligibility_and_policy_provisional"}
    result = {"contract_version": "0.1", "input_case_version": cost_export["input_case_version"],
              "plan_version": cost_export["plan_version"], "state": "needs_clarification" if blocked else "proposed",
              "selected_action_ids": sorted(selected), "retained_commitment_ids": retained,
              "remove_commitment_ids": [] if blocked else removable,
              "add_commitments": [] if blocked else additions, "issues": sorted(issues), "hypothetical": True}
    check("PlannerSelectionProposal", result)
    return result
