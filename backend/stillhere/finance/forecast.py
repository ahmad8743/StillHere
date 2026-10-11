"""Deterministic 14-day forecasts of an already reconciled USD ledger.

No clock, storage, provider, application framework, or ledger writes live here.
The proposed local input boundary is documented in docs/finance-integration.md.
"""

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HORIZON_DAYS = 14
MAX_RECORDS = 256


class FinanceInputError(ValueError):
    """Malformed input, with a stable field path and no echoed input values."""

    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


def _fail(field, message):
    raise FinanceInputError(field, message)


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        _fail(field, "Expected a nonempty string of at most 256 characters.")
    return value


def _integer(value, field, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not int or value < 0:
        _fail(field, "Expected nonnegative integer cents/count; unknown is null.")
    return value


def _boolean(value, field, nullable=False):
    if nullable and value is None:
        return None
    if type(value) is not bool:
        _fail(field, "Expected a boolean.")
    return value


def _date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        _fail(field, "Expected a YYYY-MM-DD date.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(field, "Expected a valid calendar date.")


def _instant(value, field):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        _fail(field, "Expected an RFC 3339 UTC instant.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(field, "Expected a valid UTC instant.")


def _strings(value, field):
    if not isinstance(value, list) or len(value) > MAX_RECORDS:
        _fail(field, "Expected a bounded array of strings.")
    result = [_text(item, field) for item in value]
    if len(set(result)) != len(result):
        _fail(field, "Duplicate references are not allowed.")
    return sorted(result)


def _records(value, field):
    if not isinstance(value, list) or len(value) > MAX_RECORDS:
        _fail(field, "Expected an array of at most 256 records.")
    ids = set()
    for item in value:
        if not isinstance(item, dict):
            _fail(field, "Expected object records.")
        identity = _text(item.get("id"), field + ".id")
        if identity in ids:
            _fail(field + ".id", "Duplicate record identity.")
        ids.add(identity)
    return sorted(value, key=lambda item: item["id"])


def _required(item, key, field):
    if key not in item:
        _fail(field + "." + key, "Required field is missing; use null for unknown.")
    return item[key]


def _warning(warnings, code, record_id, message, incomplete=True):
    item = {"code": code, "record_id": record_id, "message": message,
            "affects_completeness": incomplete}
    if item not in warnings:
        warnings.append(item)


def _restrictions(item, field):
    value = _required(item, "restrictions", field)
    return None if value is None else _strings(value, field + ".restrictions")


def _expense_records(records, zone):
    result = []
    for item in _records(records, "expense_commitments"):
        field = "expense_commitments." + item["id"]
        normalized = dict(item)
        if item.get("currency", "USD") != "USD":
            _fail(field + ".currency", "Only USD is supported.")
        if item.get("frequency", "daily") != "daily":
            _fail(field, "Only one-off or daily commitments are supported.")
        normalized["category"] = _text(item.get("category"), field + ".category")
        normalized["amount_cents"] = _integer(
            _required(item, "amount_cents", field), field + ".amount_cents", True)
        normalized["essential"] = _boolean(item.get("essential"), field + ".essential")
        normalized["priority"] = _integer(item.get("priority", 100), field + ".priority")
        if item.get("action_id") is not None:
            _text(item["action_id"], field + ".action_id")
        if "date" in item:
            if "start_date" in item or "end_date" in item:
                _fail(field, "Choose a one-off date or a daily date range.")
            normalized["start"] = normalized["end"] = _date(item["date"], field + ".date")
            normalized["fulfilled_cents"] = _integer(item.get("fulfilled_cents", 0),
                                                       field + ".fulfilled_cents", True)
            if "fulfilled_cents_by_date" in item:
                _fail(field, "Use fulfilled_cents for a one-off expense.")
        else:
            normalized["start"] = _date(item.get("start_date"), field + ".start_date")
            normalized["end"] = _date(item.get("end_date"), field + ".end_date")
            if "fulfilled_cents" in item or "due_at" in item:
                _fail(field, "Daily expenses use fulfilled_cents_by_date and date-level timing.")
            fulfilled = item.get("fulfilled_cents_by_date", {})
            if not isinstance(fulfilled, dict) or len(fulfilled) > MAX_RECORDS:
                _fail(field, "Expected a bounded per-date fulfillment object.")
            for day, amount in fulfilled.items():
                when = _date(day, field + ".fulfilled_cents_by_date")
                if not normalized["start"] <= when <= normalized["end"]:
                    _fail(field, "Fulfillment must fall within the expense date range.")
                _integer(amount, field + ".fulfilled_cents_by_date", True)
            normalized["fulfilled_cents_by_date"] = dict(fulfilled)
        if normalized["end"] < normalized["start"]:
            _fail(field, "Date range must be inclusive and ordered.")
        normalized["due"] = None
        if "due_at" in item:
            due = _instant(item["due_at"], field + ".due_at")
            if due.astimezone(zone).date() != normalized["start"]:
                _fail(field, "Expense date must match due_at in the case time zone.")
            normalized["due"] = due
        result.append(normalized)
    return result


def _support_records(records, scenario=False):
    result = []
    for item in _records(records, "support"):
        field = "support." + item["id"]
        normalized = dict(item)
        state = _text(item.get("state"), field + ".state")
        if state not in {"confirmed", "hypothetical", "unknown", "unavailable"}:
            _fail(field + ".state", "Unsupported support state.")
        if scenario and state != "hypothetical":
            _fail(field, "Scenario support must be explicitly hypothetical.")
        normalized["start"] = _date(item.get("start_date"), field + ".start_date")
        normalized["end"] = _date(item.get("end_date"), field + ".end_date")
        if normalized["end"] < normalized["start"]:
            _fail(field, "Date range must be inclusive and ordered.")
        normalized["categories"] = _strings(item.get("categories", []), field + ".categories")
        normalized["commitment_ids"] = _strings(item.get("commitment_ids", []),
                                                  field + ".commitment_ids")
        if not normalized["categories"] and not normalized["commitment_ids"]:
            _fail(field, "Support needs explicit categories or commitment IDs.")
        normalized["covers_full_cost"] = _boolean(item.get("covers_full_cost", False),
                                                    field + ".covers_full_cost")
        coverage = _text(item.get("household_coverage", "unknown"), field + ".household_coverage")
        if coverage not in {"full", "partial", "unknown"}:
            _fail(field, "Unsupported household coverage.")
        for key in ("total_limit_cents", "daily_limit_cents"):
            if key in item:
                normalized[key] = _integer(item[key], field + "." + key, True)
        normalized["consumed_cents"] = _integer(item.get("consumed_cents", 0),
                                                  field + ".consumed_cents")
        result.append(normalized)
    return result


def _receipt_records(records, zone):
    result = []
    aid_ids = set()
    for item in _records(records, "receipts"):
        field = "receipts." + item["id"]
        if item.get("state") != "hypothetical":
            _fail(field + ".state", "Scenario receipts must be explicitly hypothetical.")
        normalized = dict(item)
        normalized["amount_cents"] = _integer(_required(item, "amount_cents", field),
                                                 field + ".amount_cents", True)
        if item.get("currency") != "USD":
            _fail(field + ".currency", "Only USD is supported.")
        normalized["restrictions"] = _restrictions(item, field)
        normalized["date_value"] = _date(item.get("date"), field + ".date")
        normalized["available"] = None
        if "available_at" in item:
            available = _instant(item["available_at"], field + ".available_at")
            if available.astimezone(zone).date() != normalized["date_value"]:
                _fail(field, "Receipt date must match available_at in the case time zone.")
            normalized["available"] = available
        if item.get("aid_id") is not None:
            identity = _text(item["aid_id"], field + ".aid_id")
            if identity in aid_ids:
                _fail(field, "A scenario cannot receive the same aid twice.")
            aid_ids.add(identity)
        result.append(normalized)
    return result


def _aid_records(records):
    records = _records(records, "aid")
    for item in records:
        _text(item.get("stage"), "aid." + item["id"] + ".stage")
    return records


def _opening(ledger, start, zone, warnings):
    pools = []
    opening_unknown = False
    aid = {item["id"]: item for item in _aid_records(ledger.get("aid", []))}
    reflected = set()
    represented_aid = set()
    for item in _records(ledger["money_sources"], "money_sources"):
        field = "money_sources." + item["id"]
        source_type = _text(item.get("type"), field + ".type")
        if source_type not in {"cash", "account", "received_assistance"}:
            _fail(field + ".type", "Expected cash, account or received_assistance; credit/assets are not money.")
        if item.get("currency") != "USD":
            _fail(field + ".currency", "Only USD is supported.")
        balance = _integer(_required(item, "balance_cents", field), field + ".balance_cents", True)
        accessible = _boolean(_required(item, "accessible", field), field + ".accessible", True)
        restrictions = _restrictions(item, field)
        as_of_value = _required(item, "as_of", field)
        as_of = None if as_of_value is None else _instant(as_of_value, field + ".as_of")
        reflected.update(_strings(item.get("reflected_event_ids", []), field + ".reflected_event_ids"))
        aid_id = item.get("aid_id")
        if aid_id is not None:
            _text(aid_id, field + ".aid_id")
            if aid_id not in aid:
                _fail(field + ".aid_id", "Aid reference does not exist.")
            represented_aid.add(aid_id)
            if aid[aid_id].get("stage") != "received":
                _warning(warnings, "unreceived_aid_excluded", item["id"],
                         "A balance linked to unreceived aid is excluded.", False)
                continue
        if accessible is False:
            _warning(warnings, "inaccessible_funds", item["id"],
                     "Inaccessible funds are excluded from spendable money.", False)
            continue
        if accessible is None or balance is None or as_of is None:
            opening_unknown = True
            _warning(warnings, "unknown_balance", item["id"],
                     "Balance, accessibility or its as-of time is unknown; clarify the opening money.")
            continue
        if as_of > datetime.combine(start, time.min, zone):
            opening_unknown = True
            _warning(warnings, "future_balance", item["id"],
                     "A balance after forecast-start midnight cannot anchor earlier costs; reconcile or choose a later start date.")
            continue
        if as_of.astimezone(zone).date() < start:
            _warning(warnings, "balance_before_start", item["id"],
                     "A balance predates forecast start; the caller must confirm intervening events were reconciled.", False)
        freshness = item.get("freshness", "current")
        if freshness is not None:
            _text(freshness, field + ".freshness")
            if freshness not in {"current", "stale", "conflicting", "unknown"}:
                _fail(field + ".freshness", "Unsupported balance freshness.")
        if freshness is None or freshness in {"stale", "conflicting", "unknown"}:
            opening_unknown = True
            _warning(warnings, "uncertain_balance", item["id"],
                     "A stale, conflicting or unknown-freshness balance needs confirmation.")
        if "available_at" in item or "expires_at" in item:
            opening_unknown = True
            _warning(warnings, "unsupported_fund_timing", item["id"],
                     "Balance availability/expiry constraints need normalization before this slice can allocate them.")
            continue
        if restrictions is None:
            opening_unknown = True
            _warning(warnings, "unknown_restrictions", item["id"],
                     "Funds with unknown restrictions stay separate and are not allocated.")
            continue
        pools.append({"id": item["id"], "balance": balance, "restrictions": restrictions})
    for item in aid.values():
        if item.get("stage") == "received" and item["id"] not in represented_aid:
            opening_unknown = True
            _warning(warnings, "unrepresented_received_aid", item["id"],
                     "Received aid must be reconciled into a balance; the aid tracker is not added as cash.")
    for item in _records(ledger.get("actual_events", []), "actual_events"):
        if item.get("state") == "proposed":
            continue
        if item["id"] not in reflected:
            opening_unknown = True
            _warning(warnings, "unreconciled_actual_event", item["id"],
                     "An actual event is not reflected in a balance; reconciliation is required before authoritative forecasting.")
    return pools, opening_unknown


def _matches(support, expense):
    return ((not support["categories"] or expense["category"] in support["categories"])
            and (not support["commitment_ids"] or expense["id"] in support["commitment_ids"]))


def _usable_support(support, expenses, start, end, warnings):
    usable = []
    for item in support:
        if item["state"] not in {"confirmed", "hypothetical"}:
            continue
        relevant = any(_matches(item, expense) and max(start, item["start"], expense["start"])
                       <= min(end, item["end"], expense["end"]) for expense in expenses)
        if not relevant:
            continue
        unknown_limit = any(key in item and item[key] is None
                            for key in ("daily_limit_cents", "total_limit_cents"))
        has_limit = any(item.get(key) is not None
                        for key in ("daily_limit_cents", "total_limit_cents"))
        if (unknown_limit or item.get("household_coverage", "unknown") == "unknown"
                or (item.get("household_coverage") == "partial" and not has_limit)
                or (not item["covers_full_cost"] and not has_limit)
                or "quantity_limit" in item):
            _warning(warnings, "unknown_support_coverage", item["id"],
                     "Support needs known household coverage and explicit full-cost coverage or monetary limits; quantities need normalization.")
            continue
        if item["consumed_cents"] and "total_limit_cents" not in item:
            _warning(warnings, "unsupported_support_consumption", item["id"],
                     "Consumed value requires a total monetary limit; daily/quantity consumption needs normalization.")
            continue
        remaining = item.get("total_limit_cents")
        usable.append({**item, "remaining": None if remaining is None else
                       max(0, remaining - item["consumed_cents"])})
    # Confirmed coverage is used before hypothetical coverage. Stable IDs break ties.
    return sorted(usable, key=lambda item: (item["state"] != "confirmed", item["id"]))


def _calculate(ledger, expenses, support, receipts, scenario_id, label, start, zone, version):
    end = start + timedelta(days=HORIZON_DAYS - 1)
    warnings = []
    pools, opening_unknown = _opening(ledger, start, zone, warnings)
    opening_known = sum(pool["balance"] for pool in pools)
    unrestricted = sum(pool["balance"] for pool in pools if not pool["restrictions"])
    pools = [pool for pool in pools if pool["restrictions"]]
    usable_support = _usable_support(support, expenses, start, end, warnings)
    for receipt in receipts:
        if not start <= receipt["date_value"] <= end:
            _warning(warnings, "receipt_outside_horizon", receipt["id"],
                     "A hypothetical receipt outside the 14-day horizon is excluded.", False)
    days = []
    first_gap = None
    first_essential_gap = None
    for index in range(HORIZON_DAYS):
        day = start + timedelta(days=index)
        day_start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        day_end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        queue = []
        for receipt in receipts:
            if receipt["date_value"] == day:
                queue.append((receipt["available"] or day_start, 0, 0, 0, receipt["id"], receipt))
        for expense in expenses:
            if expense["start"] <= day <= expense["end"]:
                queue.append((expense["due"] or day_end, 1, not expense["essential"],
                              expense["priority"], expense["id"], expense))
        queue.sort(key=lambda entry: entry[:5])
        receipt_total = due_total = support_total = restricted_total = cash_due_total = unmet_total = 0
        unknown_receipts = unknown_expenses = False
        allocations = []
        receipt_ids = []
        daily_support = {item["id"]: item.get("daily_limit_cents") for item in usable_support}
        gaps = []
        essential_gaps = []
        for _, kind, _, _, _, item in queue:
            if kind == 0:
                receipt_ids.append(item["id"])
                amount = item["amount_cents"]
                if amount is None:
                    unknown_receipts = True
                    _warning(warnings, "unknown_receipt_amount", item["id"],
                             "A hypothetical receipt amount is unknown.")
                    continue
                receipt_total += amount
                restrictions = item["restrictions"]
                if restrictions is None:
                    _warning(warnings, "unknown_restrictions", item["id"],
                             "Hypothetical funds with unknown restrictions stay separate and are not allocated.")
                elif restrictions:
                    pools.append({"id": item["id"], "balance": amount, "restrictions": restrictions})
                else:
                    unrestricted += amount
                continue
            amount = item["amount_cents"]
            fulfilled = (item.get("fulfilled_cents", 0) if "date" in item else
                         item["fulfilled_cents_by_date"].get(day.isoformat(), 0))
            allocation = {"expense_id": item["id"], "action_id": item.get("action_id"),
                          "category": item["category"], "essential": item["essential"],
                          "amount_cents": amount, "fulfilled_cents": fulfilled,
                          "due_cents": None, "support_cents": 0, "support_ids": [],
                          "restricted_cents": 0, "restricted_source_ids": [],
                          "unrestricted_expense_cents": None, "unmet_cents": None,
                          "known_inputs_unmet_cents": None}
            allocations.append(allocation)
            if amount is None or fulfilled is None:
                unknown_expenses = True
                _warning(warnings, "unknown_expense_amount", item["id"],
                         "An expense or its reconciled fulfillment is unknown; known costs are only a subtotal.")
                continue
            due = max(0, amount - fulfilled)
            allocation["due_cents"] = due
            due_total += due
            remaining = due
            for coverage in usable_support:
                if not coverage["start"] <= day <= coverage["end"] or not _matches(coverage, item):
                    continue
                limits = [remaining]
                if coverage["remaining"] is not None:
                    limits.append(coverage["remaining"])
                if daily_support[coverage["id"]] is not None:
                    limits.append(daily_support[coverage["id"]])
                used = min(limits)
                if used:
                    remaining -= used
                    support_total += used
                    allocation["support_cents"] += used
                    allocation["support_ids"].append(coverage["id"])
                    if coverage["remaining"] is not None:
                        coverage["remaining"] -= used
                    if daily_support[coverage["id"]] is not None:
                        daily_support[coverage["id"]] -= used
            # Narrower category restrictions are spent first, then stable source ID.
            for pool in sorted(pools, key=lambda pool: (len(pool["restrictions"]), pool["id"])):
                if item["category"] not in pool["restrictions"]:
                    continue
                used = min(remaining, pool["balance"])
                if used:
                    pool["balance"] -= used
                    remaining -= used
                    restricted_total += used
                    allocation["restricted_cents"] += used
                    allocation["restricted_source_ids"].append(pool["id"])
            unmet = max(0, remaining - max(0, unrestricted))
            unrestricted -= remaining
            cash_due_total += remaining
            unmet_total += unmet
            allocation["unrestricted_expense_cents"] = remaining
            allocation["unmet_cents"] = unmet
            allocation["known_inputs_unmet_cents"] = unmet
            if unmet:
                gaps.append((item["id"], unmet))
                if item["essential"]:
                    essential_gaps.append((item["id"], unmet))
        for candidate, essential in ((gaps, False), (essential_gaps, True)):
            if candidate and (first_essential_gap if essential else first_gap) is None:
                gap = {"day": index + 1, "date": day.isoformat(),
                       "amount_cents": sum(amount for _, amount in candidate),
                       "expense_ids": [identity for identity, _ in candidate]}
                if essential:
                    first_essential_gap = gap
                else:
                    first_gap = gap
        restricted_remaining = sum(pool["balance"] for pool in pools)
        known_position = unrestricted + restricted_remaining
        days.append({"day": index + 1, "date": day.isoformat(),
                     "receipts_cents": None if unknown_receipts else receipt_total,
                     "known_receipts_cents": receipt_total, "receipt_ids": receipt_ids,
                     "expenses_due_cents": None if unknown_expenses else due_total,
                     "known_expenses_due_cents": due_total, "support_coverage_cents": support_total,
                     "restricted_coverage_cents": restricted_total,
                     "uncovered_expense_cents": None if unknown_expenses else cash_due_total,
                     "known_uncovered_expense_cents": cash_due_total,
                     "known_inputs_unmet_cents": unmet_total,
                     "known_inputs_projected_position_cents": known_position,
                     "known_inputs_unrestricted_position_cents": unrestricted,
                     "remaining_restricted_cents": restricted_remaining,
                     "expense_ids": [item["expense_id"] for item in allocations],
                     "action_ids": sorted({item["action_id"] for item in allocations if item["action_id"]}),
                     "expenses": allocations})
    complete = not any(item["affects_completeness"] for item in warnings)
    if not complete:
        _warning(warnings, "incomplete_forecast", "forecast",
                 "Missing or unresolved inputs prevent a definitive first gap or ending position; known-input subtotals do not establish coverage.")
    for row in days:
        row["projected_position_cents"] = row["known_inputs_projected_position_cents"] if complete else None
        row["unmet_cents"] = row["known_inputs_unmet_cents"] if complete else None
        if not complete:
            for expense in row["expenses"]:
                expense["unmet_cents"] = None
    assumptions = [
        "Fourteen inclusive local calendar dates; USD integer cents only.",
        "Opening balances and fulfillment are reconciled upstream; actual events are never replayed here.",
        "Aid tracker amounts are never added as cash; unreceived aid is excluded from baseline.",
        "Date-only receipts precede date-only expenses; known UTC times preserve intraday availability. Receipts win exact ties.",
        "Expenses use known time, then essential status, lower priority number, and stable ID.",
        "Confirmed support precedes hypothetical support; overlapping coverage is capped at the remaining expense.",
        "Compatible restricted funds use narrower category sets then stable ID, before unrestricted money.",
        "Negative positions represent accumulated funding gaps, not borrowing; later receipts never erase earlier gap records.",
        "Known-input subtotals exclude unresolved amounts and held funds; incomplete results do not establish coverage.",
    ]
    if scenario_id != "baseline":
        assumptions.append("Scenario receipts and support are conditional assumptions; they do not change actual money.")
    return {"contract_version": "0.1", "scenario_id": scenario_id, "label": label,
            "input_case_version": version, "time_zone": zone.key,
            "start_date": start.isoformat(), "end_date": end.isoformat(), "state": "complete" if complete else "incomplete",
            "opening_accessible_cents": None if opening_unknown else opening_known,
            "opening_known_accessible_cents": opening_known,
            "daily_projections": days, "first_gap": first_gap if complete else None,
            "first_essential_gap": first_essential_gap if complete else None,
            "known_inputs_first_gap": first_gap, "known_inputs_first_essential_gap": first_essential_gap,
            "ending_projected_position_cents": days[-1]["known_inputs_projected_position_cents"] if complete else None,
            "ending_known_inputs_position_cents": days[-1]["known_inputs_projected_position_cents"],
            "scenario_assumptions": {
                "receipts": [{key: item.get(key) for key in
                              ("id", "amount_cents", "date", "available_at", "restrictions", "aid_id")}
                             for item in receipts],
                "support": [{key: item.get(key) for key in
                             ("id", "start_date", "end_date", "categories", "commitment_ids",
                              "household_coverage", "covers_full_cost", "daily_limit_cents", "total_limit_cents", "consumed_cents")}
                            for item in support if item["state"] == "hypothetical"],
            },
            "assumptions": assumptions, "warnings": sorted(warnings, key=lambda item: (item["code"], item["record_id"]))}


def forecast_finances(ledger, *, start_date, time_zone, input_case_version, scenarios=None):
    """Return one baseline and up to three additive hypothetical forecasts.

    Accept ordinary JSON-shaped records, copied before validation/allocation.
    FinanceInputError rejects malformed dates, money, references and scenarios.
    Explicit unknowns produce incomplete forecasts with known-input subtotals.
    Financial updates, reconciliation and feasible action selection are upstream.
    """
    if not isinstance(ledger, dict):
        _fail("ledger", "Expected a ledger object.")
    ledger = deepcopy(ledger)
    start = _date(start_date, "start_date")
    if start > date.max - timedelta(days=HORIZON_DAYS):
        _fail("start_date", "The full horizon must fit within supported calendar dates.")
    _text(time_zone, "time_zone")
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError):
        _fail("time_zone", "Expected an available IANA time zone.")
    version = _integer(input_case_version, "input_case_version")
    if version < 1:
        _fail("input_case_version", "Expected a positive case version.")
    _records(_required(ledger, "money_sources", "ledger"), "money_sources")
    expenses = _expense_records(_required(ledger, "expense_commitments", "ledger"), zone)
    support = _support_records(ledger.get("support", []))
    expense_ids = {item["id"] for item in expenses}
    for item in support:
        if set(item["commitment_ids"]) - expense_ids:
            _fail("support." + item["id"] + ".commitment_ids", "Commitment reference does not exist.")
    baseline_support = [item for item in support if item["state"] == "confirmed"]
    scenario_records = deepcopy([] if scenarios is None else scenarios)
    if not isinstance(scenario_records, list) or len(scenario_records) > 3:
        _fail("scenarios", "At most three hypothetical scenarios are allowed.")
    scenario_records = _records(scenario_records, "scenarios")
    results = []
    for item in scenario_records:
        field = "scenarios." + item["id"]
        if item["id"] == "baseline":
            _fail(field, "The baseline ID is reserved.")
        _text(item.get("label"), field + ".label")
        if set(item) - {"id", "label", "receipts", "support"}:
            _fail(field, "This slice supports additive receipts/support; action replacement needs an agreed later contract.")
        additions = _support_records(item.get("support", []), scenario=True)
        for addition in additions:
            if set(addition["commitment_ids"]) - expense_ids:
                _fail(field + ".support.commitment_ids", "Commitment reference does not exist.")
        if {entry["id"] for entry in additions} & {entry["id"] for entry in support}:
            _fail(field, "Scenario support IDs must not replace ledger support.")
        receipts = _receipt_records(item.get("receipts", []), zone)
        if {entry["id"] for entry in receipts} & {entry["id"] for entry in ledger["money_sources"]}:
            _fail(field, "Receipt IDs must not duplicate opening money-source IDs.")
        aid = {entry["id"]: entry for entry in _aid_records(ledger.get("aid", []))}
        for receipt in receipts:
            if receipt.get("aid_id") is not None:
                if receipt["aid_id"] not in aid or aid[receipt["aid_id"]].get("stage") == "received":
                    _fail(field, "A hypothetical aid receipt must reference existing unreceived aid.")
        results.append(_calculate(ledger, expenses, baseline_support + additions, receipts,
                                  item["id"], item["label"], start, zone, version))
    baseline = _calculate(ledger, expenses, baseline_support, [], "baseline", "Baseline", start, zone, version)
    return {"contract_version": "0.1", "input_case_version": version, "baseline": baseline, "scenarios": results}
