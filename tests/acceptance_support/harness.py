"""Drive real CaseService transactions, without installing snapshots using SQL."""

from copy import deepcopy
from datetime import date, timedelta
import time

from backend.stillhere.contracts import validate

NOW = "2026-10-11T05:00:00Z"
ZONE = "America/Chicago"
DAY = "2026-10-11"
PROGRAM = "co_state_id_replacement"
INTAKE = {"crisis_type": "flood", "help_urgency": "essentials_today",
          "household_group": ["children_with_me"],
          "needs": ["shelter", "food_water", "lost_documents", "managing_money"],
          "current_location": {"state": "CO", "place": "Denver"}}


def day(number):
    return (date.fromisoformat(DAY) + timedelta(days=number - 1)).isoformat()


def envelope(snapshot, kind, payload, event_id, *, channel="dashboard", occurred_at=NOW):
    return {"contract_version": "0.1", "case_id": snapshot["case_id"],
            "event_id": event_id, "expected_case_version": snapshot["case_version"],
            "occurred_at": occurred_at, "channel": channel, "type": kind,
            "payload": deepcopy(payload)}


def money(identity="family_cash", amount=30000, **extra):
    return {"id": identity, "type": "cash", "currency": "USD",
            "balance_cents": amount, "accessible": True, "restrictions": [],
            "as_of": NOW, "reflected_event_ids": [], **extra}


def commitments():
    records = [{"id": kind, "category": kind, "amount_cents": amount,
                "essential": True, "priority": priority,
                "start_date": DAY, "end_date": day(14)}
               for kind, amount, priority in (("food", 2000, 1), ("lodging", 4000, 2), ("transport", 500, 3))]
    records.append({"id": "recovery", "category": "documents", "amount_cents": 3000,
                    "essential": False, "date": DAY})
    return records


def support(**extra):
    return {"id": "week_coverage", "state": "confirmed", "categories": ["food", "lodging"],
            "start_date": DAY, "end_date": day(7), "household_coverage": "full",
            "covers_full_cost": True, **extra}


def scenario(identity, receipt_day):
    return {"id": identity, "label": "Synthetic conditional aid",
            "receipts": [{"id": identity + "_receipt", "state": "hypothetical",
                          "date": day(receipt_day), "amount_cents": 50000,
                          "currency": "USD", "restrictions": []}]}


def expense(identity="spend", amount=1200, **extra):
    return {"id": identity, "kind": "expense", "amount_cents": amount,
            "currency": "USD", "source": "user_reported", "money_source_id": "family_cash",
            "category": "food", "commitment_id": "food", "commitment_date": DAY, **extra}


class Journey:
    def __init__(self, service, *, event_id="family_create", intake=True):
        self.service = service
        self.token = service.create_session()["session_token"]
        request = {"contract_version": "0.1", "event_id": event_id, "time_zone": ZONE}
        if intake:
            request["intake"] = deepcopy(INTAKE)
        self.created = self.accept(service.create_case(self.token, request))
        self.case_id = self.created["case_id"]
        self.sequence = 0

    @staticmethod
    def accept(result):
        if result["status"] not in ("applied", "already_applied"):
            raise AssertionError({"status": result["status"], "issues": result["issues"]})
        validate("CaseSnapshot", result["case_snapshot"])
        return result["case_snapshot"]

    def snapshot(self):
        return self.service.read_case(self.token, self.case_id)

    def request(self, kind, payload, event_id=None, **kwargs):
        self.sequence += 1
        return envelope(self.snapshot(), kind, payload, event_id or "acceptance_" + str(self.sequence), **kwargs)

    def send(self, kind, payload, event_id=None, **kwargs):
        request = self.request(kind, payload, event_id, **kwargs)
        return request, self.accept(self.service.execute(self.token, request))

    def correct(self, key, value):
        return self.send("fact.correct", {"fact_key": key, "value": value, "observed_at": NOW})[1]

    def finance(self, operation, record):
        return self.send("finance.update", {"operation": operation, "record": record})[1]

    def seed_finance(self):
        self.finance("set_money_source", money())
        for record in commitments():
            self.finance("set_commitment", record)
        return self.snapshot()

    def claim(self, event_id="acceptance_chat", *, seconds=60):
        self.send("conversation.message", {"message_id": event_id + "_message", "text": "Synthetic household recovery request."}, event_id, channel="chat")
        claim = self.service.claim_agent_turn(self.token, self.case_id, event_id, seconds)
        if claim is None:
            raise AssertionError("Expected a new durable agent lease")
        return {"parent": event_id, "run_id": claim["run_id"], "deadline": time.monotonic()+seconds}

    def revise(self, lease, program=PROGRAM, **kwargs):
        result = self.service.revise_agent_plan(self.token, self.case_id, lease["parent"], lease["run_id"],
                     {"program_id": program}, self.snapshot()["case_version"], lease["deadline"], **kwargs)
        return self.accept(result)

    def derive(self, lease, operation, arguments, *, expected_version=None, **kwargs):
        return self.service.execute_agent_derivation(self.token, self.case_id, lease["parent"], lease["run_id"],
                     operation, arguments, self.snapshot()["case_version"] if expected_version is None else expected_version,
                     lease["deadline"], **kwargs)

    def prepare(self, lease):
        if self.snapshot()["facts"].get("document_issuing_state", {}).get("value") != "CO":
            self.correct("document_issuing_state", "CO")
        plan = self.revise(lease)["plan"]
        action = next(item for item in plan["actions"] if item["execution_mode"] == "online")
        args = {"application_id": "application_family", "action_id": action["id"], "program_id": PROGRAM,
                "rule_version": action["rule_version"], "path_id": action["path_id"]}
        self.accept(self.derive(lease, "application.prepare", args))
        return args

    def enroll(self, *, grace=5):
        return self.send("check_in.enroll", {"consent": True, "follow_up_consent": True,
                    "due_at": "2026-10-11T05:05:00Z", "time_zone": ZONE, "grace_minutes": grace,
                    "channel": "text_simulator", "permitted_need_ids": [self.snapshot()["needs"][0]["id"]]})[1]

    def help(self):
        return self.send("help.request", {"consent": True, "message": "Synthetic food request",
                         "permitted_need_ids": [self.snapshot()["needs"][0]["id"]]})[1]
