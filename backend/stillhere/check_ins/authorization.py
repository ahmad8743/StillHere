"""Trusted caller requirements, not an authentication system.

The integrator constructs Authority from its authenticated session/service context.
Never construct it from command payloads, channels, or model-selected arguments.
"""

from dataclasses import dataclass, field

from .contracts import CheckInError, validate


@dataclass(frozen=True)
class Authority:
    case_id: str
    role: str
    subject_id: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    explicit_user_action: bool = False


AUTHORIZATION_REQUIREMENTS = {
    **{name: {"role": "household", "permission": "check_in.write", "explicit_user_action": True}
       for name in ("check_in.enroll", "check_in.reply", "check_in.pause")},
    "help.request": {"role": "household", "permission": "help.write", "explicit_user_action": True},
    **{name: {"role": "household", "permission": "location.write", "explicit_user_action": True}
       for name in ("location.share", "location.clear")},
    "follow_up.acknowledge": {"role": "operator", "permission": "follow_up.write", "explicit_user_action": False},
    "follow_up.record": {"role": "operator", "permission": "follow_up.write", "explicit_user_action": False},
    "process_due": {"role": "worker", "permission": "check_in.process", "explicit_user_action": False},
    "operator_projection": {"role": "operator", "permission": "follow_up.read", "explicit_user_action": False},
}


def authorize(case_id, operation, caller):
    requirement = AUTHORIZATION_REQUIREMENTS.get(operation)
    if requirement is None:
        raise CheckInError("unsupported_command", "$.type", "Unsupported check-in operation.")
    if not isinstance(caller, Authority) or caller.case_id != case_id or caller.role != requirement["role"] or requirement["permission"] not in caller.permissions:
        raise CheckInError("forbidden", "$", "A scoped authenticated caller is required.")
    validate("Identifier", caller.subject_id)
    if requirement["explicit_user_action"] and caller.explicit_user_action is not True:
        raise CheckInError("consent_required", "$", "The caller must attest an explicit household action.")
