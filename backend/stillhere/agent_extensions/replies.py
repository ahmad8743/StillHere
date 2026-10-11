"""Exact saved-turn question correlation; answers never execute domain commands."""

import copy

from ..contracts import InvalidInput
from ..outputs import prepare_structured_reply, validate_structured_reply
from .schema import validate

CORRELATION_FIELDS = frozenset({"reply_to_turn_id", "question_id", "choice_id", "choice_ids", "skipped"})


def normalize_reply(snapshot, reply, *, now):
    if type(reply) is str:
        # Legacy text remains compatible, including existing Markdown replies.
        if not reply.strip() or len(reply) > 8000:
            raise InvalidInput("$.text", "Assistant text must be nonblank and bounded.")
        return {"text": reply, "questions": []}
    prepared = (validate_structured_reply(snapshot, reply, now=now) if "prepared_at" in reply
                else prepare_structured_reply(snapshot, reply, now=now))
    return {key: copy.deepcopy(prepared[key]) for key in ("text", "questions")}


def correlate_answer(snapshot, payload):
    validate("CorrelatedMessage", payload)
    explicit = any(key in payload for key in CORRELATION_FIELDS)
    if not explicit:
        # Ordinary text needs no question correlation.
        return None
    if not {"reply_to_turn_id", "question_id"} <= payload.keys():
        raise InvalidInput("$.question_id", "Explicit answers require the exact saved turn and question.")
    turn = next((item for item in snapshot["conversation"]["turns"] if item["id"] == payload["reply_to_turn_id"]), None)
    if turn is None or turn["role"] != "assistant" or turn["state"] != "complete":
        raise InvalidInput("$.reply_to_turn_id", "Select a complete saved assistant turn in this case.")
    question = next((item for item in turn.get("questions", []) if item["id"] == payload["question_id"]), None)
    if question is None:
        raise InvalidInput("$.question_id", "Select a question on that exact saved turn.")
    if any(item.get("reply_to_turn_id") == turn["id"] and item.get("question_id") == question["id"]
           for item in snapshot["conversation"]["turns"] if item["role"] == "user"):
        raise InvalidInput("$.question_id", "This question already has a saved answer; replay the original event.")
    selected = ([payload["choice_id"]] if "choice_id" in payload else payload.get("choice_ids", []))
    skipped = payload.get("skipped", False)
    if skipped:
        if not question["allow_skip"] or selected:
            raise InvalidInput("$.skipped", "A skipped answer cannot select choices.")
    elif question["kind"] == "text":
        if selected:
            raise InvalidInput("$.choice_id", "Text questions do not accept choice identities.")
    else:
        if not selected or (question["kind"] == "single_choice" and len(selected) != 1):
            raise InvalidInput("$.choice_ids", "Answer cardinality must match the saved question.")
        if not set(selected) <= {item["id"] for item in question["choices"]}:
            raise InvalidInput("$.choice_ids", "Choices must belong to that exact saved question.")
    return {"reply_to_turn_id": turn["id"], "question_id": question["id"],
            "choice_ids": copy.deepcopy(selected), "skipped": skipped}
