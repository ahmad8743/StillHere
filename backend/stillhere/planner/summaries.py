"""Bounded agent views; complete plans/history stay in the authorized snapshot."""

import copy

from ..contracts import validate
from .plans import ORIGIN


def summarize_plan(plan):
    actions = []
    for action in plan["actions"]:
        if action.get("origin") != ORIGIN:
            continue
        actions.append({key: copy.deepcopy(action[key]) for key in (
            "id", "title", "status", "execution_mode", "official_url", "source_ids", "alternative_ids",
            "inability_reason", "is_current", "input_freshness", "costs")})
    diagnostics = {}
    for field in ("blockers", "questions"):
        diagnostics[field] = [{key: copy.deepcopy(item.get(key)) for key in ("node_id", "fact_key", "code", "message", "source_ids")}
                              for item in plan[field][:4]]
    summary = {"state": plan["state"], "version": plan["version"], "actions": actions,
               **diagnostics, "input_case_version": plan.get("input_case_version"),
               "pending_input_case_version": plan.get("pending_input_case_version"),
               "household_eligibility": "unknown", "blocker_count": len(plan["blockers"]),
               "question_count": len(plan["questions"]), "diagnostics_truncated": len(plan["blockers"]) > 4 or len(plan["questions"]) > 4,
               "retained_other_action_count": len(plan["actions"]) - len(actions)}
    validate("RecoveryPlanSummary", summary)
    return summary


def mutation_summary(result):
    validate("CommandResult", result)
    summary = {key: copy.deepcopy(result[key]) for key in (
        "contract_version", "event_id", "status", "received_at", "applied_case_version", "issues")}
    summary["plan_summary"] = summarize_plan(result["case_snapshot"]["plan"]) if result["case_snapshot"] else None
    validate("RecoveryMutationResult", summary)
    return summary
