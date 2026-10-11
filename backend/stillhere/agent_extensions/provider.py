"""Factory composing the existing bounded provider with validated staged replies."""

from ..agent.provider import StrandsBedrockProvider
from ..agent.tools import AgentFailure


class ExtensionProvider:
    def __init__(self, provider):
        self.provider = provider

    def reply(self, snapshot, history, user_text, context, registry):
        text = self.provider.reply(snapshot, history, user_text, context, registry)
        prepared = getattr(context, "extension_reply", None)
        if prepared is None:
            return text
        if prepared["input_case_version"] != context.expected_version:
            raise AgentFailure("stale_structured_reply", "Prepare the structured reply after the final case change.")
        return prepared


def create_provider(config, *, model=None, diagnostics=None):
    return ExtensionProvider(StrandsBedrockProvider(config, model=model, diagnostics=diagnostics))
