"""Synthetic F01–F07 data; no configuration or credentials are loaded."""

from copy import deepcopy

NOW = "2026-10-11T05:00:00Z"  # midnight in the case's Chicago zone
ZONE = "America/Chicago"
DAY = "2026-10-11"
INTAKE = {"crisis_type": "flood", "help_urgency": "essentials_today",
          "household_group": ["children_with_me"], "needs": ["shelter", "food_water", "lost_documents"],
          "current_location": {"state": "CO", "place": "Denver"}}


def family_ledger():
    return {"money_sources": [{"id": "cash_family", "type": "cash", "currency": "USD",
                              "balance_cents": 30000, "accessible": True, "restrictions": [],
                              "as_of": NOW, "reflected_event_ids": []}],
            "actual_events": [], "aid": [], "support": [],
            "expense_commitments": [
                {"id": "daily_essentials", "category": "essentials", "amount_cents": 6500,
                 "essential": True, "start_date": DAY, "end_date": "2026-10-24"},
                {"id": "day_one", "category": "documents", "amount_cents": 3000,
                 "essential": False, "date": DAY}]}


def command(snapshot, kind, payload, event_id, *, occurred_at=NOW, channel="dashboard"):
    return {"contract_version": "0.1", "case_id": snapshot["case_id"], "event_id": event_id,
            "expected_case_version": snapshot["case_version"], "occurred_at": occurred_at,
            "channel": channel, "type": kind, "payload": deepcopy(payload)}


def create_family(service):
    token = service.create_session()["session_token"]
    result = service.create_case(token, {"contract_version": "0.1", "event_id": "family_create",
                                       "time_zone": ZONE, "intake": deepcopy(INTAKE)})
    if result["status"] != "applied":
        raise AssertionError(result["issues"])
    return token, result["case_snapshot"]
