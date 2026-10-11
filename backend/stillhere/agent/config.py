"""Explicit provider settings. Importing the case API needs no SDK or secrets."""

import os
from dataclasses import dataclass
from pathlib import Path


def load_local_environment(path):
    """Only an explicit user-run CLI option loads a secret file; no automatic discovery."""
    from dotenv import dotenv_values
    if not Path(path).is_file():
        raise FileNotFoundError("The requested environment file does not exist.")
    for key, value in dotenv_values(path).items():
        if value and value.strip() and not os.environ.get(key, "").strip():
            os.environ[key] = value


@dataclass(frozen=True)
class AgentConfig:
    model_id: str = ""
    region: str = ""
    max_turns: int = 4
    max_tool_calls: int = 6
    max_output_tokens: int = 1024
    max_total_tokens: int = 12000
    timeout_seconds: int = 60
    history_turns: int = 12
    max_context_chars: int = 48000
    enable_intake: bool = False
    enable_incidents: bool = False

    def __post_init__(self):
        for key in ("max_turns", "max_tool_calls", "max_output_tokens", "max_total_tokens", "timeout_seconds", "history_turns", "max_context_chars"):
            if type(getattr(self, key)) is not int or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be a positive integer.")

    @property
    def missing_provider_settings(self):
        return tuple(name for name, value in (
            ("AWS_REGION", self.region),
            ("STILLHERE_BEDROCK_MODEL_ID", self.model_id),
        ) if not value.strip())

    @classmethod
    def from_environment(cls):
        settings = {}
        for name in ("max_turns", "max_tool_calls", "max_output_tokens", "max_total_tokens", "timeout_seconds", "history_turns", "max_context_chars"):
            value = os.environ.get("STILLHERE_AGENT_" + name.upper())
            if value:
                settings[name] = int(value)
        intake = os.environ.get("STILLHERE_AGENT_ENABLE_INTAKE", "false").lower()
        if intake not in ("true", "false"):
            raise ValueError("STILLHERE_AGENT_ENABLE_INTAKE must be true or false.")
        incidents = os.environ.get("STILLHERE_AGENT_ENABLE_INCIDENTS", "false").lower()
        if incidents not in ("true", "false"):
            raise ValueError("STILLHERE_AGENT_ENABLE_INCIDENTS must be true or false.")
        return cls(model_id=os.environ.get("STILLHERE_BEDROCK_MODEL_ID", "").strip(),
                   region=os.environ.get("AWS_REGION", "").strip(), enable_intake=intake == "true",
                   enable_incidents=incidents == "true", **settings)
