from typing import Any, Protocol

from ..models import ProviderReply


class Provider(Protocol):
    origin: str

    def complete(self, request: dict[str, Any]) -> ProviderReply: ...
