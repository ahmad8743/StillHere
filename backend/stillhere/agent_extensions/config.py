"""Independent flags; no environment-file loading or automatic provider access."""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class ExtensionConfig:
    finance_updates: bool = False
    finance_calculation: bool = False
    finance_scenarios: bool = False
    applications: bool = False
    dashboard: bool = False
    check_ins: bool = False
    structured_replies: bool = False

    def __post_init__(self):
        if any(type(getattr(self, item.name)) is not bool for item in fields(self)):
            raise ValueError("Extension flags must be booleans.")

    @classmethod
    def from_environment(cls, environment):
        # Caller supplies process environment; never inspect configuration files.
        values = {}
        for item in fields(cls):
            value = environment.get("STILLHERE_AGENT_ENABLE_" + item.name.upper(), "false").lower()
            if value not in ("true", "false"):
                raise ValueError("Extension flags must be true or false.")
            values[item.name] = value == "true"
        return cls(**values)
