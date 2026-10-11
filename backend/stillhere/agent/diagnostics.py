"""Allowlisted local smoke events; never retain exception text, prompts, or credentials."""

import json
import os
import threading
import time
from pathlib import Path


EVENTS = frozenset({
    "smoke_started", "config_ready", "config_missing", "run_started", "provider_started",
    "sdk_import_started", "sdk_import_complete", "bedrock_client_started", "bedrock_client_ready",
    "model_invocation_started", "model_invocation_complete", "tool_call_complete",
    "provider_failed", "run_timeout", "run_complete", "run_failed", "smoke_passed", "smoke_failed",
    "access_check_started", "access_identity_started", "access_profile_started",
    "access_form_started", "access_availability_started", "access_check_complete",
})
ACCESS_STATES = {
    "account_match": frozenset({"MATCH", "MISMATCH", "NOT_CHECKED", "UNKNOWN"}),
    "profile": frozenset({"ACTIVE", "NOT_APPLICABLE", "UNKNOWN"}),
    "use_case": frozenset({"SUBMITTED", "NOT_VISIBLE", "NOT_APPLICABLE", "UNKNOWN"}),
    "agreement": frozenset({"AVAILABLE", "PENDING", "NOT_AVAILABLE", "ERROR", "UNKNOWN"}),
    "authorization": frozenset({"AUTHORIZED", "NOT_AUTHORIZED", "UNKNOWN"}),
    "entitlement": frozenset({"AVAILABLE", "NOT_AVAILABLE", "UNKNOWN"}),
    "region": frozenset({"AVAILABLE", "NOT_AVAILABLE", "UNKNOWN"}),
}


def safe_access_status(status):
    return {key: value if isinstance(value := status.get(key), str) and value in allowed else "UNKNOWN"
            for key, allowed in ACCESS_STATES.items()}
CODES = frozenset({
    "agent_not_configured", "agent_dependency_missing", "agent_provider_unavailable",
    "agent_timeout", "agent_interrupted", "agent_limit_or_stop", "agent_tool_limit",
    "agent_context_limit", "invalid_agent_reply", "agent_run_inactive", "version_conflict",
    "required_fact_missing", "replay_failed", "incident_context_missing", "incident_sources_unavailable",
    "AccessDeniedException", "ValidationException",
    "ResourceNotFoundException", "ThrottlingException", "ServiceQuotaExceededException",
    "ModelTimeoutException", "ModelNotReadyException", "ModelErrorException",
    "ServiceUnavailableException", "InternalServerException", "UnrecognizedClientException",
    "ExpiredTokenException", "InvalidSignatureException", "IncompleteSignature", "FTUFormNotFilled",
})
ERROR_TYPES = frozenset({
    "ClientError", "NoCredentialsError", "PartialCredentialsError", "ProfileNotFound",
    "UnauthorizedSSOTokenError", "SSOTokenLoadError", "CredentialRetrievalError",
    "TokenRetrievalError", "EndpointConnectionError", "ConnectTimeoutError",
    "ReadTimeoutError", "SSLError", "ImportError", "ModuleNotFoundError",
    "ParamValidationError", "EventStreamError", "BotoCoreError", "EventLoopException",
    "TypeError", "ValueError", "RuntimeError", "KeyError", "AttributeError",
})

# Match only fixed service phrases. Output labels never contain any substring
# copied from an AWS message, which may include identifiers or request values.
AWS_REASON_RULES = (
    ("anthropic_use_case_required", ("model use case details have not been submitted", "fill out the anthropic use case", "ftuformnotfilled")),
    ("account_model_access_denied", ("not available for this account", "access to bedrock models is not allowed for this account")),
    ("operation_not_allowed", ("operation not allowed",)),
    ("model_identifier_invalid", ("provided model identifier is invalid",)),
    ("inference_profile_required", ("on-demand throughput isn",)),
    ("temperature_unsupported", ("doesn't support the temperature field", "does not support the temperature field")),
    ("top_p_unsupported", ("doesn't support the topp field", "does not support the topp field")),
    ("stop_sequences_unsupported", ("doesn't support the stopsequences field", "does not support the stopsequences field")),
    ("marketplace_subscription_permission", ("aws-marketplace:subscribe",)),
    ("payment_method_required", ("invalid_payment_instrument", "invalid payment method")),
    ("iam_permission_denied", ("not authorized to perform",)),
)
REASONS = frozenset(reason for reason, _ in AWS_REASON_RULES) | {"unclassified"}


def aws_failure_reason(code, message):
    if code == "FTUFormNotFilled":
        return "anthropic_use_case_required"
    if code not in ("AccessDeniedException", "ValidationException", "ResourceNotFoundException"):
        return None
    if isinstance(message, str) and len(message) <= 4096:
        lowered = message.lower()
        for reason, phrases in AWS_REASON_RULES:
            if any(phrase in lowered for phrase in phrases):
                return reason
    return "unclassified"


class SafeDiagnostics:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.provider_failure = None

    def record(self, event, *, code=None, error_type=None, reason=None, access_status=None):
        if event not in EVENTS:
            raise ValueError("Unknown diagnostic event.")
        entry = {"event": event, "elapsed_seconds": round(time.monotonic() - self.started, 3)}
        if code is not None:
            entry["code"] = code if code in CODES else "other_failure"
        if error_type is not None:
            entry["error_type"] = error_type if error_type in ERROR_TYPES else "Exception"
        if reason is not None:
            entry["reason"] = reason if reason in REASONS else "unclassified"
        if access_status is not None:
            entry["access_status"] = safe_access_status(access_status)
        with self.lock:
            if event == "provider_failed":
                # The CLI can display the same sanitized fields for this run
                # without rereading a log that may include earlier attempts.
                self.provider_failure = {key: entry[key] for key in ("code", "reason", "error_type") if key in entry}
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(descriptor, "w") as output:
                output.write(json.dumps(entry, sort_keys=True) + "\n")

    def failure(self, error):
        # Botocore generates named ClientError subclasses, and Strands wraps them
        # in EventLoopException. Inspect a bounded exception chain, never str(error),
        # args, notes, traceback locals or request state. Match response messages
        # against fixed phrases without retaining their text or any values.
        pending, seen, error_type = [error], set(), "Exception"
        while pending and len(seen) < 8:
            current = pending.pop(0)
            if id(current) in seen:
                continue
            seen.add(id(current))
            names = [base.__name__ for base in type(current).__mro__]
            if "ClientError" in names:
                code, reason = None, None
                response = getattr(current, "response", None)
                if isinstance(response, dict) and isinstance(response.get("Error"), dict):
                    candidate = response["Error"].get("Code")
                    code = candidate if isinstance(candidate, str) and candidate in CODES else "other_failure"
                    reason = aws_failure_reason(code, response["Error"].get("Message"))
                self.record("provider_failed", code=code, error_type="ClientError", reason=reason)
                return
            recognized = next((name for name in names if name in ERROR_TYPES), None)
            if recognized is not None:
                error_type = recognized
            for nested in (current.__cause__, current.__context__):
                if isinstance(nested, BaseException) and id(nested) not in seen:
                    pending.append(nested)
        self.record("provider_failed", error_type=error_type)


def record(diagnostics, event, **fields):
    """Diagnostics must not change the outcome of an accepted command if storage fails."""
    if diagnostics is not None:
        try:
            diagnostics.record(event, **fields)
        except OSError:
            pass


def failure(diagnostics, error):
    if diagnostics is not None:
        try:
            diagnostics.failure(error)
        except OSError:
            pass
