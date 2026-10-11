"""Pure dashboard preparation and revalidation, never durable publication."""

import copy

from .validation import fail, identity, instant, validate_preparation, validate_shape


# References are exact record identities, never paths, URLs or executable controls.
KIND_DOMAINS = {
    "urgent_resource": {"resource"},
    "next_step": {"action"},
    "task_list": {"action"},
    "blocker_controls": {"action", "need", "evidence", "blocker"},
    "evidence_checklist": {"evidence"},
    "aid_tracker": {"application", "aid"},
    "finance_overview": {"money_source", "expense", "aid", "support", "forecast"},
    "scenario_comparison": {"scenario"},
    "check_in": {"schedule", "report", "attempt", "follow_up"},
    "source_details": {"source"},
}
REQUIRES_RECORD = {"urgent_resource", "next_step", "scenario_comparison"}
MAX_SNAPSHOT_RECORDS = 4096


def _section(snapshot, key):
    value = snapshot.get(key, {})
    if type(value) is not dict:
        fail("$.snapshot." + key, "Snapshot section must be an object.")
    return value


def _index(snapshot):
    records = {}
    count = 0

    def add(items, domain, parent):
        nonlocal count
        if type(items) is not list or len(items) > MAX_SNAPSHOT_RECORDS:
            fail("$.snapshot", "Snapshot record collection is invalid or too large.")
        for record in items:
            count += 1
            if count > MAX_SNAPSHOT_RECORDS or type(record) is not dict:
                fail("$.snapshot", "Snapshot record collection is invalid or too large.")
            identifier = record.get("id")
            # Existing forecasts have scenario_id rather than id; no synthetic IDs.
            if identifier is None and domain in ("forecast", "scenario"):
                identifier = record.get("scenario_id")
            if identifier is None:
                # Legacy untyped blockers/reports need not have record identities.
                continue
            validate_shape("Id", identifier)
            if identifier in records:
                fail("$.snapshot", "Snapshot record identities are ambiguous.", "ambiguous_reference")
            records[identifier] = (domain, record, parent)

    resources = _section(snapshot, "resources")
    plan = _section(snapshot, "plan")
    finance = _section(snapshot, "finance")
    ledger = _section(finance, "ledger")
    check_in = _section(snapshot, "check_in")
    add(resources.get("items", []), "resource", resources)
    add(plan.get("actions", []), "action", plan)
    add(plan.get("blockers", []), "blocker", plan)
    for key, domain in (("needs", "need"), ("evidence", "evidence"),
                        ("applications", "application"), ("sources", "source")):
        add(snapshot.get(key, []), domain, {})
    for key, domain in (("money_sources", "money_source"), ("expense_commitments", "expense"),
                        ("aid", "aid"), ("support", "support")):
        add(ledger.get(key, []), domain, finance)
    baseline = finance.get("baseline")
    if baseline is not None:
        add([baseline], "forecast", finance)
    add(finance.get("scenarios", []), "scenario", finance)
    for key, domain in (("schedule", "schedule"), ("last_report", "report")):
        if check_in.get(key) is not None:
            add([check_in[key]], domain, check_in)
    add(check_in.get("attempts", []), "attempt", check_in)
    add(snapshot.get("follow_ups", []), "follow_up", check_in)
    return records


def _freshness(record, version, now):
    signals = []
    for key in ("freshness", "input_freshness"):
        if key in record:
            value = record[key]
            signals.append(value if value in ("current", "stale", "unknown") else "unknown")
    if record.get("state") in ("stale", "pending") or record.get("is_current") is False:
        signals.append("stale")
    if record.get("state") in ("unknown", "conflicting", "not_requested", "not_calculated", "unavailable"):
        signals.append("unknown")
    if "pending_input_case_version" in record:
        signals.append("stale")
    if "input_case_version" in record:
        input_version = record["input_case_version"]
        if type(input_version) is not int or input_version < 1 or input_version > version:
            signals.append("unknown")
        else:
            signals.append("current" if input_version == version else "stale")
    for key in ("computed_at", "observed_at", "retrieved_at", "updated_at", "as_of", "reviewed_at"):
        if key in record:
            try:
                observed = instant(record[key], "$.snapshot.timestamp")
                signals.append("unknown" if observed > now else "current")
            except ValueError:
                signals.append("unknown")
    if record.get("expires_at") is not None:
        try:
            signals.append("stale" if instant(record["expires_at"], "$.snapshot.expires_at") <= now else "current")
        except ValueError:
            signals.append("unknown")
    return _combine(signals) if signals else None


def _combine(signals):
    signals = [signal for signal in signals if signal is not None]
    return "stale" if "stale" in signals else "unknown" if not signals or "unknown" in signals else "current"


def _source_signals(record, index, version, now):
    signals = []
    source_ids = record.get("source_ids", [])
    if type(source_ids) is not list or len(source_ids) > 24:
        fail("$.snapshot.source_ids", "Source references must be a bounded array.")
    for source_id in source_ids:
        validate_shape("Id", source_id)
        source = index.get(source_id)
        if source is None or source[0] != "source":
            fail("$.snapshot.source_ids", "Referenced record has a dangling source.", "dangling_reference")
        signals.append(_freshness(source[1], version, now))
    return signals


def _record_state(identifier, entry, index, version, now):
    domain, record, parent = entry
    signals = [_freshness(record, version, now)]
    if parent:
        signals.append(_freshness(parent, version, now))
        if domain == "resource" and type(parent.get("search")) is dict:
            signals.append(_freshness(parent["search"], version, now))
    signals.extend(_source_signals(record, index, version, now))
    availability = record.get("availability", "unknown")
    if type(availability) is dict:
        signals.append(_freshness(availability, version, now))
        signals.extend(_source_signals(availability, index, version, now))
        capacity = availability
        availability = capacity.get("state", "unknown")
        if availability in ("confirmed_available", "confirmed_unavailable"):
            try:
                timed = instant(capacity.get("observed_at"), "$.snapshot.availability.observed_at") <= now
            except ValueError:
                timed = False
            if not timed or not capacity.get("source_ids"):
                availability = "unknown"
                signals.append("unknown")
    elif domain == "resource" and availability != "unknown":
        # A bare capacity label has no capacity observation/evidence wrapper.
        availability = "unknown"
        signals.append("unknown")
    if availability not in ("confirmed_available", "confirmed_unavailable", "unknown"):
        availability = "unknown"
    state = record.get("state", record.get("status", "unknown"))
    # Status vocabulary belongs to each unfinished domain; unknown strings never
    # become display text or a new output capability.
    if type(state) is not str or state not in STATES:
        state = "unknown"
    return {"record_id": identifier, "freshness": _combine(signals), "state": state,
            "availability": availability if domain == "resource" else None,
            "data_mode": record.get("data_mode") if record.get("data_mode") in
                         ("live", "cached", "seeded", "sandbox") else None}


STATES = frozenset(("unknown", "available", "no_match", "unavailable", "not_requested", "not_calculated",
                    "pending", "provisional", "complete", "incomplete", "current", "stale", "ready", "blocked",
                    "waiting", "completed", "skipped", "covered", "uncovered", "missing", "user_reported",
                    "source_supported", "conflicting", "proposed", "confirmed", "hypothetical", "received",
                    "unreceived", "not_enrolled", "scheduled", "due", "reminder_attempted", "overdue", "answered",
                    "paused", "canceled", "requested", "assigned_acknowledged", "contact_attempted", "outcome_recorded"))


def _component_state(component, snapshot, index, version, now):
    rows = [_record_state(identifier, index[identifier], index, version, now) for identifier in component["record_ids"]]
    kind = component["kind"]
    section_key = {"urgent_resource": "resources", "next_step": "plan", "task_list": "plan",
                   "blocker_controls": "plan", "finance_overview": "finance", "scenario_comparison": "finance",
                   "check_in": "check_in"}.get(kind)
    section = _section(snapshot, section_key) if section_key else {}
    state = section.get("state", section.get("status", "unknown"))
    if type(state) is not str or state not in STATES:
        state = "unknown"
    signals = [row["freshness"] for row in rows]
    if section:
        signals.append(_freshness(section, version, now))
        if kind == "urgent_resource" and type(section.get("search")) is dict:
            signals.append(_freshness(section["search"], version, now))
    return {"component_id": component["id"], "state": state,
            "freshness": _combine(signals), "record_states": rows}


def prepare_dashboard_publication(snapshot, arguments, *, now):
    """Prepare publish_dashboard_components arguments from an authorized snapshot.

    The backend supplies snapshot and now. Model arguments contain components
    only. The returned proposal is detached JSON, not a grant or a saved result.
    """
    case_id, version = identity(snapshot)
    clock = instant(now, "$.now")
    validate_shape("PublishDashboardArguments", arguments)
    index = _index(snapshot)
    components = copy.deepcopy(arguments["components"])
    seen = set()
    previous_order = -1
    for component in components:
        if component["id"] in seen:
            fail("$.components", "Component identities must be unique.")
        seen.add(component["id"])
        if component["display_order"] <= previous_order:
            fail("$.components", "Components must have unique increasing display order.")
        previous_order = component["display_order"]
        if component["kind"] in REQUIRES_RECORD and not component["record_ids"]:
            fail("$.components.record_ids", "This component requires a persisted record reference.")
        for identifier in component["record_ids"]:
            if identifier not in index:
                fail("$.components.record_ids", "Component references an absent record.", "dangling_reference")
            if index[identifier][0] not in KIND_DOMAINS[component["kind"]]:
                fail("$.components.record_ids", "Record type is incompatible with the component kind.", "reference_kind")
    result = {"contract_version": "0.1", "status": "prepared", "case_id": case_id,
              "input_case_version": version, "prepared_at": now, "components": components,
              "component_states": [_component_state(item, snapshot, index, version, clock) for item in components]}
    validate_shape("DashboardPublication", result)
    return result


def build_dashboard_descriptor(snapshot, *, component_id, kind, record_ids, display_order, now):
    """Build one compatible descriptor after validating its snapshot references."""
    descriptor = {"id": component_id, "kind": kind, "record_ids": record_ids, "display_order": display_order}
    return prepare_dashboard_publication(snapshot, {"components": [descriptor]}, now=now)["components"][0]


def validate_dashboard_publication(snapshot, prepared, *, now):
    """Revalidate within CaseService's transaction immediately before publication.

    A fresh result is returned so time-dependent source expiry cannot be hidden
    by metadata prepared earlier. Never writes or changes case_version.
    """
    validate_shape("DashboardPublication", prepared)
    validate_preparation(snapshot, prepared, now)
    original = prepare_dashboard_publication(snapshot, {"components": prepared["components"]}, now=prepared["prepared_at"])
    if original != prepared:
        fail("$.component_states", "Prepared metadata does not match the snapshot.", "invalid_preparation")
    return prepare_dashboard_publication(snapshot, {"components": prepared["components"]}, now=now)
