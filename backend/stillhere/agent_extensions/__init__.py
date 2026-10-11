"""Opt-in household adapters. Persistence and authority belong to CaseService."""

from .config import ExtensionConfig
from .registry import ExtensionRegistry, create_registry
from .replies import correlate_answer, normalize_reply

__all__ = ["ExtensionConfig", "ExtensionRegistry", "create_registry", "correlate_answer", "normalize_reply"]
