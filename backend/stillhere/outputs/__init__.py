"""Framework-free output slice. CaseService remains the sole durable writer."""

from .dashboard import KIND_DOMAINS, build_dashboard_descriptor, prepare_dashboard_publication, validate_dashboard_publication
from .replies import build_follow_up_question, prepare_structured_reply, validate_structured_reply
from .validation import OutputValidationError, validate_shape

__all__ = ["OutputValidationError", "prepare_dashboard_publication", "validate_dashboard_publication",
           "prepare_structured_reply", "validate_structured_reply", "build_dashboard_descriptor",
           "build_follow_up_question", "validate_shape", "KIND_DOMAINS"]
