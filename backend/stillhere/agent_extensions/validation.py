"""Household finance cannot manufacture backend accounting ownership or trust."""

from ..contracts import InvalidInput
from .schema import bounded

RESERVED = frozenset({"origin", "planner_cost_id", "planner_commitment_id", "rule_id", "rule_version",
                      "actual_event_ids", "verification_state", "agency_receipts", "agency_outcome",
                      "authority", "role", "permissions", "consent", "provenance", "data_mode"})


def validate_household_financial_input(payload):
    bounded(payload, 16000)
    stack = [payload]
    while stack:
        value = stack.pop()
        if type(value) is dict:
            if RESERVED & value.keys():
                raise InvalidInput("$.payload", "Household financial input cannot supply backend ownership or authority.")
            stack.extend(value.values())
        elif type(value) is list:
            stack.extend(value)
    for key in ("record", "replacement"):
        record = payload.get(key, {})
        if type(record) is dict and "source" in record and record["source"] != "user_reported":
            raise InvalidInput("$.payload", "Household actual-event provenance is user_reported.")
