"""Synthetic scripted provider, explicitly unsuitable for model-performance claims."""

from typing import Any

from ..models import ProviderReply, ToolCall


class FixtureProvider:
    origin = "synthetic"

    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self.index = 0

    def complete(self, request: dict[str, Any]) -> ProviderReply:
        if self.index >= len(self.script):
            raise ValueError("Synthetic script exhausted; no model fallback")
        entry = self.script[self.index]
        self.index += 1
        return ProviderReply(calls=[ToolCall.model_validate(entry)], cost_usd="0")
