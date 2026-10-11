"""Bounded structured replies; choices are conversational data, never commands."""

import copy

from .validation import fail, identity, instant, plain_text, validate_preparation, validate_shape


def _proposal(proposal):
    # Preserve the provider's existing string reply API without modifying it.
    if type(proposal) is str:
        proposal = {"text": proposal}
    validate_shape("StructuredReplyArguments", proposal)
    result = {"text": proposal["text"], "questions": copy.deepcopy(proposal.get("questions", []))}
    plain_text(result["text"], "$.text")
    identities = set()
    for question in result["questions"]:
        plain_text(question["prompt"], "$.questions.prompt")
        choices = question["choices"]
        if (question["kind"] == "text" and choices) or (question["kind"] != "text" and len(choices) < 2):
            fail("$.questions.choices", "Text questions have no choices; choice questions need two to six choices.")
        for item in [question] + choices:
            if item["id"] in identities:
                fail("$.questions", "Question and choice identities must be unique within the reply.")
            identities.add(item["id"])
        for choice in choices:
            plain_text(choice["label"], "$.questions.choices.label")
    return result


def prepare_structured_reply(snapshot, proposal, *, now):
    """Return a result ready for CaseService validation and an assistant-turn commit."""
    case_id, version = identity(snapshot)
    instant(now, "$.now")
    result = {"contract_version": "0.1", "status": "prepared", "case_id": case_id,
              "input_case_version": version, "prepared_at": now, **_proposal(proposal)}
    validate_shape("StructuredReplyResult", result)
    return result


def build_follow_up_question(*, question_id, prompt, kind, choices=None):
    """Build display-only question data; skips are always permitted."""
    question = {"id": question_id, "prompt": prompt, "kind": kind,
                "choices": [] if choices is None else choices, "allow_skip": True}
    return _proposal({"text": "Follow-up question", "questions": [question]})["questions"][0]


def validate_structured_reply(snapshot, prepared, *, now):
    validate_shape("StructuredReplyResult", prepared)
    validate_preparation(snapshot, prepared, now)
    return prepare_structured_reply(snapshot, {"text": prepared["text"], "questions": prepared["questions"]}, now=now)
