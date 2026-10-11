"""Pure, bounded financial proposals. Authorization and persistence belong to C01.

No implicit matching, clock, configuration, IO, or inferred money lives here.
The audit journal is a bounded integration proposal, not a durable event store.
"""

from copy import deepcopy
import hashlib
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .forecast import (FinanceInputError, MAX_RECORDS, _boolean, _date, _fail,
                       _instant, _integer, _records, _required, _strings, _text,
                       forecast_finances)

COLLECTIONS = ("money_sources", "expense_commitments", "actual_events", "aid", "support")
AID_STAGES = {"unknown", "suggested", "applied", "pending", "approved", "denied", "received"}
ACTUAL_OPERATIONS = {"record_expense": "expense", "record_receipt": "receipt",
                     "record_transfer": "transfer"}


class _Clarification(Exception):
    def __init__(self, field, message):
        self.field, self.message = field, message


def _ask(field, message):
    raise _Clarification(field, message)


def _plain(value, field):
    """Reject Python-only objects and nonfinite/floating monetary shortcuts."""
    if value is None or type(value) in (bool, int, str):
        return
    if isinstance(value, list):
        if len(value) > MAX_RECORDS:
            _fail(field, "Array exceeds the bounded record limit.")
        for item in value:
            _plain(item, field)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            _plain(item, field + "." + key)
        return
    _fail(field, "Expected ordinary JSON data without floats.")


def _zone(value):
    _text(value, "time_zone")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        _fail("time_zone", "Expected an available IANA time zone.")


def _map(ledger, collection):
    return {item["id"]: item for item in _records(ledger.get(collection, []), collection)}


def _get(ledger, collection, identity):
    _text(identity, collection + ".id")
    item = _map(ledger, collection).get(identity)
    if item is None:
        _fail(collection, "Record reference does not exist.")
    return item


def _put(ledger, collection, record):
    values = _map(ledger, collection)
    values[record["id"]] = deepcopy(record)
    ledger[collection] = _records(list(values.values()), collection)


def _validate(ledger, when, zone):
    _plain(ledger, "ledger")
    forecast_finances(ledger, start_date=when.astimezone(zone).date().isoformat(),
                     time_zone=zone.key, input_case_version=1)
    for item in _records(ledger.get("aid", []), "aid"):
        if item["stage"] not in AID_STAGES:
            _fail("aid.stage", "Unsupported bounded aid stage.")
        if "amount_cents" in item:
            _integer(item["amount_cents"], "aid.amount_cents", True)
        if "expected_date" in item and item["expected_date"] is not None:
            _date(item["expected_date"], "aid.expected_date")
        if "restrictions" in item and item["restrictions"] is not None:
            _strings(item["restrictions"], "aid.restrictions")


def _fingerprint(payload, effective_at, time_zone):
    # Receipt time and transport version are deliberately outside logical identity.
    data = {"payload": payload, "effective_at": effective_at, "time_zone": time_zone}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True).encode()).hexdigest()


def _run_proposal(ledger, payload, *, event_id, effective_at, received_at, time_zone, mutate):
    try:
        _plain(payload, "payload")
        if not isinstance(payload, dict) or not isinstance(ledger, dict):
            _fail("payload", "Expected ledger and payload objects.")
        _text(event_id, "event_id")
        effective = _instant(effective_at, "effective_at")
        _instant(received_at, "received_at")
        zone = _zone(time_zone)
        fingerprint = _fingerprint(payload, effective.isoformat(), zone.key)
        history = deepcopy(_records(ledger.get("finance_updates", []), "finance_updates"))
        previous = next((entry for entry in history if entry["id"] == event_id), None)
        if previous is not None:
            if previous.get("fingerprint") != fingerprint:
                _fail("event_id", "Event identity was already used for different logical input.")
            return {"status": "applied", "replayed": True, "next_ledger": deepcopy(ledger),
                    "changed_record_ids": [], "reconciliation_notes": [], "issues": [],
                    "original_changed_record_ids": deepcopy(previous["changed_record_ids"])}
        if len(history) >= MAX_RECORDS:
            _fail("finance_updates", "Audit capacity reached; CaseService must archive with replay identity retained.")
        _validate(ledger, effective, zone)
        proposed = deepcopy(ledger)
        notes = []
        mutate(proposed, payload, effective, zone, event_id, notes)
        _validate(proposed, effective, zone)
        changes = []
        changed_ids = []
        for collection in (*COLLECTIONS, "scenarios"):
            before = _map(ledger, collection)
            after = _map(proposed, collection)
            for identity in sorted(before.keys() | after.keys()):
                if before.get(identity) != after.get(identity):
                    changes.append({"collection": collection, "record_id": identity,
                                    "before": deepcopy(before.get(identity)),
                                    "after": deepcopy(after.get(identity))})
                    changed_ids.append(collection + ":" + identity)
        audit = {"id": event_id, "fingerprint": fingerprint, "payload": deepcopy(payload),
                 "effective_at": effective_at, "received_at": received_at,
                 "changed_record_ids": changed_ids, "changes": changes,
                 "reconciliation_notes": deepcopy(notes)}
        proposed["finance_updates"] = history + [audit]
        return {"status": "applied", "replayed": False, "next_ledger": proposed,
                "changed_record_ids": changed_ids, "reconciliation_notes": notes, "issues": []}
    except (FinanceInputError, _Clarification) as error:
        return {"status": "needs_clarification" if isinstance(error, _Clarification) else "rejected",
                "replayed": False, "next_ledger": None, "changed_record_ids": [],
                "reconciliation_notes": [], "issues": [{"code": "clarify_finance" if
                isinstance(error, _Clarification) else "invalid_finance", "field": error.field,
                "message": error.message if isinstance(error, _Clarification) else str(error),
                "retryable": False}]}


def _only(payload, keys):
    if set(payload) - ({"operation"} | set(keys)):
        _fail("payload", "Unsupported operation fields.")


def _known(value, field):
    if value is None:
        _ask(field, "Confirm the unknown amount before applying actual money.")
    return _integer(value, field)


def _compatible(origin, destination, field):
    if origin is None or destination is None:
        _ask(field, "Confirm restrictions before moving or combining funds.")
    if origin and (not destination or not set(destination).issubset(origin)):
        _fail(field, "Moving funds must preserve or narrow their explicit restrictions.")


def _event(raw, effective, zone):
    if not isinstance(raw, dict):
        _fail("record", "Expected an actual event object.")
    record = deepcopy(raw)
    allowed = {"id", "kind", "amount_cents", "currency", "source", "money_source_id",
               "to_money_source_id", "category", "date", "effective_at", "state",
               "commitment_id", "commitment_date", "aid_id", "restrictions", "matching_refs"}
    if set(record) - allowed:
        _fail("record", "Unsupported actual-event fields.")
    _text(record.get("id"), "record.id")
    _text(record.get("kind"), "record.kind")
    if record["kind"] not in {"expense", "receipt", "transfer"}:
        _fail("record.kind", "Expected expense, receipt or transfer.")
    _text(record.get("source"), "record.source")
    if record.get("currency") != "USD":
        _fail("record.currency", "Only USD is supported.")
    _integer(_required(record, "amount_cents", "record"), "record.amount_cents", True)
    _text(record.get("money_source_id"), "record.money_source_id")
    record["effective_at"] = record.get("effective_at", effective.isoformat())
    when = _instant(record["effective_at"], "record.effective_at")
    day = when.astimezone(zone).date().isoformat()
    record["date"] = record.get("date", day)
    _date(record["date"], "record.date")
    if record["date"] != day:
        _fail("record.date", "Actual date must match its effective time in the case time zone.")
    record["state"] = record.get("state", "posted")
    _text(record["state"], "record.state")
    if record["state"] not in {"posted", "proposed"}:
        _fail("record.state", "Expected posted or proposed; pending imports are proposed.")
    record["matching_refs"] = _strings(record.get("matching_refs", []), "record.matching_refs")
    kind = record["kind"]
    if kind == "expense":
        _text(record.get("category"), "record.category")
    if kind == "transfer":
        _text(record.get("to_money_source_id"), "record.to_money_source_id")
        if record["to_money_source_id"] == record["money_source_id"]:
            _fail("record", "Transfer endpoints must be distinct.")
    if kind != "expense" and any(key in record for key in ("category", "commitment_id", "commitment_date")):
        _fail("record", "Only spending may fulfill an expense commitment.")
    if kind != "receipt" and any(key in record for key in ("aid_id", "restrictions")):
        _fail("record", "Only receipts may carry aid and incoming restrictions.")
    if kind != "transfer" and "to_money_source_id" in record:
        _fail("record.to_money_source_id", "Only transfers have a destination source.")
    for key in ("commitment_id", "aid_id"):
        if key in record:
            _text(record[key], "record." + key)
    if "commitment_date" in record:
        _date(record["commitment_date"], "record.commitment_date")
        if "commitment_id" not in record:
            _fail("record.commitment_date", "An occurrence requires an explicit commitment match.")
    if "restrictions" in record and record["restrictions"] is not None:
        record["restrictions"] = _strings(record["restrictions"], "record.restrictions")
    return record


def _commitment(ledger, event, zone):
    if event["kind"] != "expense":
        return None, None
    if "commitment_id" not in event:
        # Similarity is a clarification hint, never an automatic match.
        candidates = [item for item in _map(ledger, "expense_commitments").values()
                      if item["category"] == event["category"] and
                      item.get("date", item.get("start_date")) <= event["date"] <=
                      item.get("date", item.get("end_date"))]
        if candidates:
            _ask("record.commitment_id", "Choose the matching commitment, or explicitly confirm this spending is additional.")
        return None, None
    if event["commitment_id"] == "additional":
        if "additional" in _map(ledger, "expense_commitments"):
            _fail("record.commitment_id", "The additional-spending sentinel conflicts with a commitment identity.")
        return None, None
    item = _get(ledger, "expense_commitments", event["commitment_id"])
    day = event.get("commitment_date", event["date"])
    if item["category"] != event["category"] or not (item.get("date", item.get("start_date")) <=
        day <= item.get("date", item.get("end_date"))):
        _fail("record.commitment_id", "Expense category and occurrence must match the commitment.")
    return item, day


def _fulfill(item, day, amount):
    if "date" in item:
        old = _known(item.get("fulfilled_cents", 0), "commitment.fulfilled_cents")
        item["fulfilled_cents"] = old + amount
        result = item["fulfilled_cents"]
    else:
        values = item.setdefault("fulfilled_cents_by_date", {})
        old = _known(values.get(day, 0), "commitment.fulfilled_cents_by_date")
        values[day] = old + amount
        result = values[day]
    if result < 0:
        _ask("commitment", "Existing fulfillment cannot safely reverse this match; reconcile the occurrence.")


def _sources(ledger, event):
    result = [_get(ledger, "money_sources", event["money_source_id"])]
    if event["kind"] == "transfer":
        result.append(_get(ledger, "money_sources", event["to_money_source_id"]))
    return result


def _matched_total(ledger, commitment_id, day, exclude_id):
    return sum(_known(event.get("amount_cents"), "actual_events.amount_cents")
               for event in ledger.get("actual_events", []) if event["id"] != exclude_id
               and event.get("state") != "proposed" and event.get("commitment_id") == commitment_id
               and event.get("commitment_date", event.get("date")) == day)


def _post(ledger, event, zone, reflected_ids, notes, fulfillment_reflected=False):
    sources = _sources(ledger, event)
    commitment, day = _commitment(ledger, event, zone)
    for other in _map(ledger, "actual_events").values():
        if other["id"] != event["id"] and set(other.get("matching_refs", [])) & set(event["matching_refs"]):
            _ask("record.matching_refs", "This import/deposit reference already belongs to another event; explicitly reconcile it.")
    aid = None
    if "aid_id" in event:
        aid = _get(ledger, "aid", event["aid_id"])
        other_receipt = aid.get("actual_receipt_id")
        if other_receipt is not None and other_receipt != event["id"]:
            _ask("record.aid_id", "Aid is already matched to another receipt; reconcile before recording again.")
        if sources[0].get("aid_id") != aid["id"]:
            _fail("record.aid_id", "Aid receipt requires a dedicated source linked by aid_id.")
        if sources[0]["type"] != "received_assistance":
            _fail("record.aid_id", "Aid receipt must use a received-assistance source.")
    if event["state"] == "proposed":
        if reflected_ids:
            _fail("balance_reflected_source_ids", "A proposed event cannot be reflected in an actual balance.")
        _put(ledger, "actual_events", event)
        notes.append({"code": "proposed_only", "record_id": event["id"]})
        return
    amount = _known(event["amount_cents"], "record.amount_cents")
    if event["kind"] != "receipt":
        for source in sources:
            if source.get("aid_id") and _get(ledger, "aid", source["aid_id"])["stage"] != "received":
                _ask("money_source.aid_id", "Unreceived aid cannot be spent or moved as actual money.")
    elif sources[0].get("aid_id") and event.get("aid_id") != sources[0]["aid_id"]:
        _fail("record.aid_id", "A dedicated aid source requires its explicit aid receipt match.")
    if event["kind"] == "expense":
        restrictions = sources[0]["restrictions"]
        if restrictions is None:
            _ask("money_source.restrictions", "Confirm source restrictions before allocating actual spending.")
        if restrictions and event["category"] not in restrictions:
            _fail("record.category", "Expense is incompatible with this source's restrictions.")
    if event["kind"] == "transfer":
        _compatible(sources[0]["restrictions"], sources[1]["restrictions"], "record.restrictions")
    if event["kind"] == "receipt":
        incoming = _required(event, "restrictions", "record")
        if aid is not None:
            aid_restrictions = _required(aid, "restrictions", "aid")
            if aid_restrictions is not None:
                aid_restrictions = _strings(aid_restrictions, "aid.restrictions")
            if incoming != aid_restrictions:
                _fail("record.restrictions", "Receipt restrictions must match the linked aid record.")
        _compatible(incoming, sources[0]["restrictions"], "record.restrictions")
    deltas = [-amount] if event["kind"] == "expense" else [amount]
    if event["kind"] == "transfer":
        deltas = [-amount, amount]
    if set(reflected_ids) - {item["id"] for item in sources}:
        _fail("balance_reflected_source_ids", "Reflected sources must be event endpoints.")
    event["balance_epochs"] = {}
    event["balance_effects"] = {}
    event["snapshot_reflected_source_ids"] = []
    when = _instant(event["effective_at"], "record.effective_at")
    for source, delta in zip(sources, deltas):
        ids = source.setdefault("reflected_event_ids", [])
        reflected = source["id"] in reflected_ids or event["id"] in ids
        anchor = None if source["as_of"] is None else _instant(source["as_of"], "money_source.as_of")
        if reflected:
            if anchor is None or when > anchor:
                _ask("balance_reflected_source_ids", "A reflected event needs a balance snapshot at or after its effective time.")
            event["snapshot_reflected_source_ids"].append(source["id"])
        else:
            if source.get("freshness", "current") != "current":
                _ask("money_source.freshness", "Reconcile the stale/conflicting/unknown balance before applying arithmetic.")
            if delta < 0 and source["accessible"] is not True:
                _ask("money_source.accessible", "Confirm source accessibility before applying new spending or outgoing transfers.")
            if (delta < 0 and ((source.get("available_at") is not None and
                    when < _instant(source["available_at"], "money_source.available_at")) or
                    (source.get("expires_at") is not None and
                    when >= _instant(source["expires_at"], "money_source.expires_at")))):
                _ask("money_source", "Actual spending conflicts with entered fund availability/expiry; reconcile timing.")
            if anchor is None or when < anchor:
                _ask("record.effective_at", "Confirm whether this event is included in the later or unknown balance snapshot.")
            balance = _known(source["balance_cents"], "money_source.balance_cents")
            if balance + delta < 0:
                _ask("money_source.balance_cents", "Actual spending exceeds the entered balance; reconcile instead of creating negative money.")
            source["balance_cents"] = balance + delta
            source["as_of"] = event["effective_at"]
        if event["id"] not in ids:
            ids.append(event["id"])
        source["reflected_event_ids"] = _strings(ids, "money_source.reflected_event_ids")
        event["balance_epochs"][source["id"]] = source.get("balance_epoch")
        event["balance_effects"][source["id"]] = delta
    if commitment is not None:
        if fulfillment_reflected:
            fulfilled = (commitment.get("fulfilled_cents", 0) if "date" in commitment else
                         commitment.get("fulfilled_cents_by_date", {}).get(day, 0))
            total = amount + _matched_total(ledger, commitment["id"], day, event["id"])
            if _known(fulfilled, "commitment.fulfilled_cents") < total:
                _fail("commitment_fulfillment_reflected", "Entered fulfillment does not cover the matched actual amount.")
            event["fulfillment_was_reflected"] = True
        else:
            _fulfill(commitment, day, amount)
        event["commitment_date"] = day
    elif fulfillment_reflected:
        _fail("commitment_fulfillment_reflected", "Reflected fulfillment requires a matched commitment.")
    if aid is not None:
        event["aid_before_receipt"] = {"stage": aid["stage"], "actual_receipt_id": aid.get("actual_receipt_id")}
        aid["stage"], aid["actual_receipt_id"] = "received", event["id"]
    _put(ledger, "actual_events", event)
    notes.append({"code": "actual_reconciled", "record_id": event["id"],
                  "source_ids": [source["id"] for source in sources],
                  "commitment_id": event.get("commitment_id"), "aid_id": event.get("aid_id")})


def _replace_actual(ledger, payload, effective, zone, notes):
    old = _get(ledger, "actual_events", payload.get("record_id"))
    replacement = _event(payload.get("replacement"), effective, zone)
    if replacement["id"] != old["id"]:
        _fail("replacement.id", "Reconciliation/correction preserves the actual event identity.")
    if set(old.get("matching_refs", [])) - set(replacement["matching_refs"]):
        _fail("replacement.matching_refs", "A revision must preserve prior import/deposit references.")
    if payload["operation"] == "reconcile_event" and old.get("state") != "proposed" and "balance_effects" not in old:
        endpoints = {item["id"] for item in _sources(ledger, replacement)}
        if set(payload.get("balance_reflected_source_ids", [])) != endpoints:
            _ask("balance_reflected_source_ids", "Legacy reconciliation must explicitly acknowledge every endpoint snapshot.")
        if old.get("commitment_id") and not payload.get("commitment_fulfillment_reflected", False):
            _ask("commitment_fulfillment_reflected", "Confirm whether legacy fulfillment already includes this event.")
        ledger["actual_events"] = [item for item in ledger["actual_events"] if item["id"] != old["id"]]
        _post(ledger, replacement, zone, payload["balance_reflected_source_ids"], notes,
              payload.get("commitment_fulfillment_reflected", False))
        notes.append({"code": "legacy_snapshot_reconciled", "record_id": old["id"]})
        return
    if old.get("state") != "proposed":
        effects = old.get("balance_effects")
        if not isinstance(effects, dict):
            _ask("record_id", "Legacy actual records require explicit snapshot reconciliation before correction.")
        for source_id, delta in effects.items():
            source = _get(ledger, "money_sources", source_id)
            if (source_id in old.get("snapshot_reflected_source_ids", []) or
                    source.get("balance_epoch") != old.get("balance_epochs", {}).get(source_id)):
                _ask("record_id", "A balance snapshot already includes this event; correct the snapshot and fulfillment explicitly.")
            value = _known(source["balance_cents"], "money_source.balance_cents") - delta
            if value < 0:
                _ask("record_id", "Reversing this receipt would overdraw later spending; reconcile a new balance.")
            source["balance_cents"] = value
            source["reflected_event_ids"].remove(old["id"])
            # Reapply against the original temporal anchor, without moving the final as_of backwards.
        commitment, day = _commitment(ledger, old, zone)
        if commitment is not None:
            _fulfill(commitment, day, -old["amount_cents"])
        if old.get("aid_id"):
            aid = _get(ledger, "aid", old["aid_id"])
            previous = old.get("aid_before_receipt")
            if not isinstance(previous, dict):
                _ask("record_id", "Prior aid stage is unknown; explicitly reconcile the aid receipt.")
            aid.update(previous)
    ledger["actual_events"] = [item for item in ledger["actual_events"] if item["id"] != old["id"]]
    anchors = {item["id"]: item["as_of"] for item in _sources(ledger, replacement)}
    # Arithmetic corrections use the current known balance, but preserve its newest timestamp.
    if old.get("state") != "proposed":
        if replacement["money_source_id"] != old["money_source_id"] or replacement.get("to_money_source_id") != old.get("to_money_source_id"):
            _ask("replacement", "Changing posted endpoints requires explicit balance reconciliation.")
        if replacement["effective_at"] != old["effective_at"] or replacement["kind"] != old["kind"]:
            _ask("replacement", "Changing posted timing or kind requires explicit balance reconciliation.")
        for source in _sources(ledger, replacement):
            source["as_of"] = replacement["effective_at"]
    _post(ledger, replacement, zone, payload.get("balance_reflected_source_ids", []), notes,
          payload.get("commitment_fulfillment_reflected", False))
    for source in _sources(ledger, replacement):
        if anchors[source["id"]] is not None and (source["as_of"] is None or
                _instant(anchors[source["id"]], "as_of") > _instant(source["as_of"], "as_of")):
            source["as_of"] = anchors[source["id"]]
    notes.append({"code": "auditable_revision", "record_id": old["id"]})


def _snapshot_correction(ledger, payload, effective, zone, event_id, notes):
    """Correct an event absorbed by later snapshots using explicit reconciled totals."""
    old = _get(ledger, "actual_events", payload.get("record_id"))
    new = _event(payload.get("replacement"), effective, zone)
    if set(old.get("matching_refs", [])) - set(new["matching_refs"]):
        _fail("replacement.matching_refs", "A correction must preserve prior import/deposit references.")
    if (new["id"] != old["id"] or new["kind"] != old.get("kind") or
            new["money_source_id"] != old.get("money_source_id") or
            new.get("to_money_source_id") != old.get("to_money_source_id") or
            new.get("aid_id") != old.get("aid_id") or new["state"] != "posted"):
        _fail("replacement", "Snapshot correction preserves identity, kind, endpoints and aid link, and remains posted.")
    sources = _sources(ledger, new)
    snapshots = payload.get("source_snapshots")
    if not isinstance(snapshots, list) or len(snapshots) != len(sources):
        _fail("source_snapshots", "Supply exactly one explicit snapshot for every endpoint.")
    seen = set()
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            _fail("source_snapshots", "Expected snapshot objects.")
        if set(snapshot) - {"money_source_id", "balance_cents", "as_of", "reflected_event_ids", "freshness"}:
            _fail("source_snapshots", "Unsupported snapshot fields.")
        source_id = snapshot.get("money_source_id")
        _text(source_id, "source_snapshots.money_source_id")
        if source_id in seen or source_id not in {item["id"] for item in sources}:
            _fail("source_snapshots", "Duplicate or unrelated endpoint snapshot.")
        seen.add(source_id)
        # Reuse the explicit refresh contract, preserving all acknowledged references.
        _mutate(ledger, {"operation": "set_balance", **snapshot}, effective, zone, event_id, notes)
    occurrences = {}
    for event in (old, new):
        commitment, day = _commitment(ledger, event, zone)
        if commitment is not None:
            occurrences[(commitment["id"], day)] = commitment
    fulfillment = payload.get("commitment_fulfillment", [])
    if not isinstance(fulfillment, list) or len(fulfillment) != len(occurrences):
        _fail("commitment_fulfillment", "Supply explicit fulfillment for every old/new matched occurrence.")
    seen = set()
    for item in fulfillment:
        if not isinstance(item, dict) or set(item) != {"commitment_id", "date", "fulfilled_cents"}:
            _fail("commitment_fulfillment", "Expected commitment_id, date and fulfilled_cents.")
        _text(item["commitment_id"], "commitment_fulfillment.commitment_id")
        _date(item["date"], "commitment_fulfillment.date")
        key = (item["commitment_id"], item["date"])
        if key in seen or key not in occurrences:
            _fail("commitment_fulfillment", "Duplicate or unrelated fulfillment occurrence.")
        seen.add(key)
        value = _integer(item["fulfilled_cents"], "commitment_fulfillment.fulfilled_cents")
        commitment = occurrences[key]
        other_total = _matched_total(ledger, key[0], key[1], old["id"])
        new_total = new["amount_cents"] if new.get("commitment_id") == key[0] and new.get("commitment_date", new["date"]) == key[1] else 0
        if value < other_total + _known(new_total, "record.amount_cents"):
            _fail("commitment_fulfillment", "Fulfillment cannot erase other matched actual spending.")
        if "date" in commitment:
            commitment["fulfilled_cents"] = value
        else:
            commitment.setdefault("fulfilled_cents_by_date", {})[key[1]] = value
    ledger["actual_events"] = [item for item in ledger["actual_events"] if item["id"] != old["id"]]
    _post(ledger, new, zone, sorted(seen_source["id"] for seen_source in sources), notes,
          fulfillment_reflected=bool(occurrences and new.get("commitment_id") != "additional" and new.get("commitment_id")))
    notes.append({"code": "snapshot_correction_reconciled", "record_id": old["id"]})


def _mutate(ledger, payload, effective, zone, event_id, notes):
    operation = payload.get("operation")
    _text(operation, "operation")
    if operation in ACTUAL_OPERATIONS:
        _only(payload, {"record", "balance_reflected_source_ids", "commitment_fulfillment_reflected"})
        event = _event(payload.get("record"), effective, zone)
        if event["kind"] != ACTUAL_OPERATIONS[operation]:
            _fail("record.kind", "Actual kind must match the operation.")
        if event["id"] in _map(ledger, "actual_events"):
            _ask("record.id", "Actual identity exists; use explicit reconciliation or correction.")
        reflected = _strings(payload.get("balance_reflected_source_ids", []), "balance_reflected_source_ids")
        fulfillment_reflected = _boolean(payload.get("commitment_fulfillment_reflected", False), "commitment_fulfillment_reflected")
        _post(ledger, event, zone, reflected, notes, fulfillment_reflected)
    elif operation in {"reconcile_event", "correct_actual"}:
        _only(payload, {"record_id", "replacement", "balance_reflected_source_ids", "reason", "commitment_fulfillment_reflected"})
        _text(payload.get("reason"), "reason")
        _strings(payload.get("balance_reflected_source_ids", []), "balance_reflected_source_ids")
        _boolean(payload.get("commitment_fulfillment_reflected", False), "commitment_fulfillment_reflected")
        if operation == "correct_actual" and (payload.get("balance_reflected_source_ids") or payload.get("commitment_fulfillment_reflected")):
            _fail("payload", "Arithmetic corrections cannot also claim snapshot-reflected effects.")
        _replace_actual(ledger, payload, effective, zone, notes)
    elif operation == "reconcile_correction":
        _only(payload, {"record_id", "replacement", "reason", "source_snapshots", "commitment_fulfillment"})
        _text(payload.get("reason"), "reason")
        _snapshot_correction(ledger, payload, effective, zone, event_id, notes)
    elif operation == "set_money_source":
        _only(payload, {"record"})
        raw = payload.get("record")
        if not isinstance(raw, dict):
            _fail("record", "Expected a money-source object.")
        _text(raw.get("id"), "record.id")
        if raw.get("id") in _map(ledger, "money_sources"):
            _fail("record.id", "Use set_balance or correct_record to revise an existing source.")
        if set(raw) & {"balance_epoch"}:
            _fail("record", "Balance epoch is backend-owned.")
        for reference in _strings(raw.get("reflected_event_ids", []), "record.reflected_event_ids"):
            event = _get(ledger, "actual_events", reference)
            if event.get("state") == "proposed" or raw["id"] not in {event.get("money_source_id"), event.get("to_money_source_id")}:
                _fail("record.reflected_event_ids", "Reflected event must be a posted endpoint match.")
        _put(ledger, "money_sources", raw)
    elif operation == "set_balance":
        _only(payload, {"money_source_id", "balance_cents", "as_of", "reflected_event_ids", "freshness", "reason"})
        source = _get(ledger, "money_sources", payload.get("money_source_id"))
        amount = _integer(_required(payload, "balance_cents", "payload"), "balance_cents", True)
        anchor = _required(payload, "as_of", "payload")
        if anchor is not None:
            _instant(anchor, "as_of")
        ids = _strings(_required(payload, "reflected_event_ids", "payload"), "reflected_event_ids")
        if set(source.get("reflected_event_ids", [])) - set(ids):
            _ask("reflected_event_ids", "A refresh must explicitly retain previously reconciled event references.")
        for identity in set(ids) - set(source.get("reflected_event_ids", [])):
            event = _get(ledger, "actual_events", identity)
            if event.get("state") == "proposed" or source["id"] not in {event.get("money_source_id"), event.get("to_money_source_id")}:
                _fail("reflected_event_ids", "Only posted endpoint events may be reflected in a balance.")
        if source["as_of"] is not None and anchor is not None and _instant(anchor, "as_of") < _instant(source["as_of"], "as_of"):
            _ask("as_of", "A balance refresh cannot silently replace a newer anchor with an older one.")
        for identity in ids:
            event = _map(ledger, "actual_events").get(identity)
            if event and event.get("effective_at") and (anchor is None or _instant(event["effective_at"], "effective_at") > _instant(anchor, "as_of")):
                _fail("reflected_event_ids", "Reflected event occurs after the proposed snapshot.")
        source.update(balance_cents=amount, as_of=anchor, reflected_event_ids=ids,
                      freshness=payload.get("freshness", "current"), balance_epoch=event_id)
        notes.append({"code": "balance_snapshot", "record_id": source["id"]})
    elif operation in {"set_commitment", "set_aid", "set_support", "correct_record"}:
        _only(payload, {"record", "collection", "reason"} if operation == "correct_record" else {"record"})
        collection = {"set_commitment": "expense_commitments", "set_aid": "aid", "set_support": "support"}.get(operation, payload.get("collection"))
        _text(collection, "collection")
        if collection not in {"money_sources", "expense_commitments", "aid", "support"}:
            _fail("collection", "Use correct_actual for actual events; unsupported correction collection.")
        record = payload.get("record")
        if not isinstance(record, dict):
            _fail("record", "Expected a replacement record object.")
        _text(record.get("id"), "record.id")
        old = _map(ledger, collection).get(record["id"])
        if operation == "correct_record":
            _text(payload.get("reason"), "reason")
            if old is None:
                _fail("record.id", "A correction must reference an existing record.")
        if collection == "money_sources":
            # Explicit restriction/evidence corrections retain the reconciled money and links.
            for key in ("balance_cents", "as_of", "reflected_event_ids", "balance_epoch", "aid_id", "type", "currency"):
                if record.get(key) != old.get(key):
                    _ask("record." + key, "Money/restriction corrections require an explicit balance/source reconciliation.")
        if collection == "expense_commitments" and old is not None:
            matched = [event for event in _map(ledger, "actual_events").values()
                       if event.get("commitment_id") == old["id"] and event.get("state") != "proposed"]
            if matched and any(record.get(key) != old.get(key) for key in
                               ("category", "date", "start_date", "end_date", "fulfilled_cents", "fulfilled_cents_by_date")):
                _ask("record", "Matched fulfillment/date/category changes require correction of the actual match first.")
        if collection == "aid":
            if record.get("stage") == "received":
                event = _get(ledger, "actual_events", record.get("actual_receipt_id"))
                if event.get("aid_id") != record["id"] or event.get("state") != "posted":
                    _fail("record.actual_receipt_id", "Received aid requires a posted matching receipt.")
            if old is not None and old.get("stage") == "received" and any(record.get(key) != old.get(key) for key in ("stage", "actual_receipt_id", "restrictions")):
                _ask("record", "Correct the matching receipt before revising received aid accounting.")
        _put(ledger, collection, record)
    else:
        _fail("operation", "Unsupported bounded financial operation.")


def apply_financial_update(ledger, update, *, event_id, effective_at, received_at, time_zone):
    """Return applied/clarification/rejected and a detached proposed ledger.

    Same event ID + logical payload replays without effects; changed input is
    rejected. Only accepted proposals append before/after audits. Unknown actual
    amounts and ambiguous matches leave the entire supplied ledger unchanged.
    """
    return _run_proposal(ledger, update, event_id=event_id, effective_at=effective_at,
                         received_at=received_at, time_zone=time_zone, mutate=_mutate)
