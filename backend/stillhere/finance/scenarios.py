"""Plain-data action-cost comparison using the unchanged forecast engine."""

from copy import deepcopy

from .forecast import (_fail, _records, _strings, _text, forecast_finances)
from .updates import _only, _plain, _put, _run_proposal


def validate_financial_scenario(ledger, scenario, *, start_date, time_zone,
                                action_alternatives=None):
    """Validate one scenario and return its detached comparison ledger.

    Alternatives are synthetic/provider-neutral {id, label, costs,
    replaces_commitment_ids}. Only explicitly named, unfulfilled nonessential
    action commitments can be replaced. Essential expenses are always retained.
    This validates financial inputs, not planner feasibility or availability.
    """
    _plain(scenario, "scenario")
    _plain(action_alternatives, "action_alternatives")
    if not isinstance(scenario, dict):
        _fail("scenario", "Expected a scenario object.")
    if set(scenario) - {"id", "label", "receipts", "support", "alternative_ids"}:
        _fail("scenario", "Unsupported scenario fields.")
    _text(scenario.get("id"), "scenario.id")
    _text(scenario.get("label"), "scenario.label")
    selected = _strings(scenario.get("alternative_ids", []), "scenario.alternative_ids")
    alternatives = {}
    # Validate every offered alternative, even when not selected; no hidden malformed costs.
    for alternative in _records([] if action_alternatives is None else action_alternatives,
                                "action_alternatives"):
        if set(alternative) - {"id", "label", "costs", "replaces_commitment_ids"}:
            _fail("action_alternatives", "Unsupported action-cost fields.")
        _text(alternative.get("label"), "action_alternatives.label")
        costs = _records(alternative.get("costs"), "action_alternatives.costs")
        if not costs:
            _fail("action_alternatives.costs", "Supply dated costs explicitly; use zero for a known free action or null for unknown cost.")
        for cost in costs:
            _text(cost.get("action_id"), "action_alternatives.costs.action_id")
            if cost.get("fulfilled_cents", 0) != 0 or cost.get("fulfilled_cents_by_date", {}):
                _fail("action_alternatives.costs", "Hypothetical action costs cannot claim actual fulfillment.")
        trial = deepcopy(ledger)
        trial["expense_commitments"] = deepcopy(costs)
        trial["support"] = []  # Existing support references the original ledger, not an isolated cost list.
        forecast_finances(trial, start_date=start_date, time_zone=time_zone, input_case_version=1)
        _strings(alternative.get("replaces_commitment_ids", []), "action_alternatives.replaces_commitment_ids")
        alternatives[alternative["id"]] = alternative
    if set(selected) - alternatives.keys():
        _fail("scenario.alternative_ids", "Selected alternative is absent from the supplied action-cost snapshot.")
    comparison = deepcopy(ledger)
    commitments = {item["id"]: item for item in _records(ledger.get("expense_commitments"), "expense_commitments")}
    replaced, added = set(), set()
    all_original_ids = set(commitments)
    for identity in selected:
        alternative = alternatives[identity]
        for old_id in alternative.get("replaces_commitment_ids", []):
            if old_id in replaced:
                _fail("scenario.alternative_ids", "Selected alternatives overlap a replacement; choose one path explicitly.")
            if old_id not in commitments:
                _fail("action_alternatives.replaces_commitment_ids", "Replacement commitment does not exist.")
            old = commitments[old_id]
            if old["essential"] or not old.get("action_id"):
                _fail("action_alternatives.replaces_commitment_ids", "Essential or non-action expenses cannot be deleted by a scenario.")
            if old.get("fulfilled_cents", 0) != 0 or old.get("fulfilled_cents_by_date", {}):
                _fail("action_alternatives.replaces_commitment_ids", "Fulfilled/unknown action spending cannot be replaced.")
            if any(event.get("commitment_id") == old_id for event in ledger.get("actual_events", [])):
                _fail("action_alternatives.replaces_commitment_ids", "An action with actual/proposed matches cannot be replaced.")
            if any(old_id in support.get("commitment_ids", []) for support in ledger.get("support", [])):
                _fail("action_alternatives.replaces_commitment_ids", "Support references the old commitment; supply an explicitly remapped alternative.")
            replaced.add(old_id)
        for cost in alternative["costs"]:
            if cost["id"] in all_original_ids or cost["id"] in added:
                _fail("action_alternatives.costs.id", "Action cost identities must not collide with ledger or selected costs.")
            added.add(cost["id"])
            commitments[cost["id"]] = deepcopy(cost)
    comparison["expense_commitments"] = [commitments[key] for key in sorted(commitments) if key not in replaced]
    normalized = deepcopy(scenario)
    normalized["alternative_ids"] = selected
    additive = {key: normalized[key] for key in ("id", "label", "receipts", "support") if key in normalized}
    # The existing validator preserves all receipt/aid/support/restriction semantics.
    forecast_finances(comparison, start_date=start_date, time_zone=time_zone,
                     input_case_version=1, scenarios=[additive])
    return {"scenario": normalized, "comparison_ledger": comparison,
            "replaced_commitment_ids": sorted(replaced), "added_commitment_ids": sorted(added)}


def compare_financial_scenarios(ledger, *, start_date, time_zone, input_case_version,
                                scenarios=None, action_alternatives=None):
    """Return baseline plus up to three independent scenarios with action costs."""
    scenarios = deepcopy(ledger.get("scenarios", []) if scenarios is None else scenarios)
    if not isinstance(scenarios, list) or len(scenarios) > 3:
        _fail("scenarios", "At most three hypothetical scenarios are allowed.")
    results = forecast_finances(ledger, start_date=start_date, time_zone=time_zone,
                               input_case_version=input_case_version)
    for scenario in _records(scenarios, "scenarios"):
        saved = scenario.get("action_cost_snapshot")
        if saved is not None and action_alternatives is not None and saved != action_alternatives:
            _fail("action_alternatives", "Stored scenario costs differ; explicitly refresh scenario.set before comparing.")
        bare = {key: value for key, value in scenario.items()
                if key not in {"action_cost_snapshot", "forecast_start_date"}}
        prepared = validate_financial_scenario(ledger, bare, start_date=start_date,
                                              time_zone=time_zone, action_alternatives=saved if saved is not None else action_alternatives)
        additive = {key: scenario[key] for key in ("id", "label", "receipts", "support") if key in scenario}
        forecast = forecast_finances(prepared["comparison_ledger"], start_date=start_date,
                                     time_zone=time_zone, input_case_version=input_case_version,
                                     scenarios=[additive])["scenarios"][0]
        forecast["scenario_assumptions"]["alternative_ids"] = prepared["scenario"]["alternative_ids"]
        forecast["scenario_assumptions"]["replaced_commitment_ids"] = prepared["replaced_commitment_ids"]
        forecast["scenario_assumptions"]["action_costs"] = [deepcopy(item) for item in
            prepared["comparison_ledger"]["expense_commitments"] if item["id"] in prepared["added_commitment_ids"]]
        if forecast["scenario_assumptions"]["alternative_ids"]:
            forecast["assumptions"].append("Action costs are caller-supplied hypothetical data; feasibility is not established by finance. Essential expenses are retained.")
        results["scenarios"].append(forecast)
    return results


def set_financial_scenario(ledger, scenario, *, event_id, effective_at, received_at,
                           time_zone, start_date, action_alternatives=None):
    """Propose scenario.set storage with replay/audit; actual money never changes.

    Store the reviewed cost snapshot with the scenario so a later forecast does
    not silently use a changed planner quote. Pass that snapshot back explicitly
    to compare_financial_scenarios. A quote refresh is a new scenario.set event.
    """
    payload = {"operation": "set_scenario", "scenario": deepcopy(scenario),
               "start_date": start_date, "action_alternatives": deepcopy(action_alternatives)}

    def mutate(proposed, update, effective, zone, identity, notes):
        _only(update, {"scenario", "start_date", "action_alternatives"})
        prepared = validate_financial_scenario(proposed, update["scenario"], start_date=update["start_date"],
                                              time_zone=zone.key, action_alternatives=update["action_alternatives"])
        saved = prepared["scenario"]
        saved["action_cost_snapshot"] = deepcopy(update["action_alternatives"] or [])
        saved["forecast_start_date"] = start_date
        _put(proposed, "scenarios", saved)
        if len(proposed["scenarios"]) > 3:
            _fail("scenarios", "At most three scenarios can be stored.")
        notes.append({"code": "hypothetical_only", "record_id": saved["id"]})

    return _run_proposal(ledger, payload, event_id=event_id, effective_at=effective_at,
                         received_at=received_at, time_zone=time_zone, mutate=mutate)
