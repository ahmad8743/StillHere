"""Pure integration decisions; CaseService alone commits derived outputs."""

from copy import deepcopy

from .forecast import _fail, _instant, _integer, _strings, _text


def invalidate_financial_outputs(prior_forecasts, *, target_case_version):
    version = _integer(target_case_version, "target_case_version")
    if version < 1:
        _fail("target_case_version", "Expected a positive case version.")
    result = deepcopy(prior_forecasts) if prior_forecasts is not None else {}
    if not isinstance(result, dict):
        _fail("prior_forecasts", "Expected a forecast object or null.")
    result.update(state="pending", pending_input_case_version=version)
    return result


def prepare_forecast_publication(forecasts, *, current_case_version, computed_at,
                                 publication_event_id, prior_forecasts=None):
    """Decide whether a calculated input version still matches the current case.

    A service must repeat this comparison inside its write transaction, and
    guard active agent/run identity independently. This helper performs no lock.
    """
    if not isinstance(forecasts, dict):
        _fail("forecasts", "Expected a forecast bundle.")
    version = _integer(current_case_version, "current_case_version")
    source = _integer(forecasts.get("input_case_version"), "input_case_version")
    if min(version, source) < 1:
        _fail("case_version", "Expected positive case versions.")
    _instant(computed_at, "computed_at")
    _text(publication_event_id, "publication_event_id")
    scenarios = forecasts.get("scenarios", [])
    if not isinstance(scenarios, list) or len(scenarios) > 3:
        _fail("forecasts.scenarios", "Expected at most three scenario projections.")
    for projection in [forecasts.get("baseline"), *scenarios]:
        if not isinstance(projection, dict) or projection.get("input_case_version") != source:
            _fail("forecasts", "Every projection must have the bundle input version.")
        if projection.get("state") not in {"complete", "incomplete"}:
            _fail("forecasts", "Only calculated complete/incomplete projections can be published.")
    if source != version:
        return {"status": "conflict", "reason": "stale_finance_inputs",
                "proposed_finance": invalidate_financial_outputs(prior_forecasts, target_case_version=version)}
    result = deepcopy(forecasts)
    result.update(computed_at=computed_at, publication_event_id=publication_event_id,
                  state="incomplete" if any(item["state"] == "incomplete" for item in
                  [result["baseline"], *result["scenarios"]]) else "current")
    result.pop("pending_input_case_version", None)
    return {"status": "applied", "proposed_finance": result}


def finance_reassessment(previous_forecasts, next_forecasts, *, changed_record_ids):
    """Return an advisory request, never modify saved plans/completed actions."""
    changed_record_ids = _strings(changed_record_ids, "changed_record_ids")
    baseline = next_forecasts["baseline"]
    before = (previous_forecasts or {}).get("baseline", {})
    reasons = []
    if baseline["state"] == "incomplete":
        reasons.append("finance_inputs_need_clarification")
    for field in ("first_gap", "first_essential_gap"):
        old, new = before.get(field), baseline.get(field)
        if new is not None and (old is None or new["date"] < old["date"] or
                (new["date"] == old["date"] and new["amount_cents"] > old["amount_cents"])):
            reasons.append("essential_gap_worsened" if field == "first_essential_gap" else "funding_gap_worsened")
        elif old is not None and new is None and baseline["state"] == "complete":
            reasons.append("funding_gap_resolved" if field == "first_gap" else "essential_gap_resolved")
        elif baseline["state"] == "complete" and new != old:
            reasons.append("funding_gap_changed" if field == "first_gap" else "essential_gap_changed")
    if any(item.startswith("expense_commitments:") for item in changed_record_ids):
        reasons.append("commitments_changed")
    if any(item.startswith(("aid:", "support:")) for item in changed_record_ids):
        reasons.append("aid_or_support_changed")
    if before and any(before.get(field) != baseline.get(field) for field in
                      ("opening_accessible_cents", "opening_known_accessible_cents")):
        reasons.append("available_money_changed")
    return {"required": bool(reasons), "reasons": reasons,
            "input_case_version": next_forecasts["input_case_version"],
            "changed_record_ids": sorted(set(changed_record_ids)),
            "preserve_completed_actions": True}
