import json
from pathlib import Path
from typing import Any

from ..models import ProviderReply, Trace
from ..util import digest, write_json


class RecordingMismatch(RuntimeError):
    pass


class RecordedProvider:
    def __init__(self, trace: Trace) -> None:
        self.origin: str = trace.origin
        self.calls = [e.payload for e in trace.events if e.kind == "model"]
        self.index = 0

    def complete(self, request: dict[str, Any]) -> ProviderReply:
        if self.index >= len(self.calls):
            raise RecordingMismatch("Recording exhausted; network fallback forbidden")
        saved = self.calls[self.index]
        if digest(request) != digest(saved["request"]):
            raise RecordingMismatch(
                f"Model request changed at occurrence {self.index}; new recording required"
            )
        self.index += 1
        return ProviderReply.model_validate(saved["response"])


def save_trace(path: Path, trace: Trace) -> None:
    write_json(
        path,
        {
            "schema_version": 1,
            "trace": trace.model_dump(),
            "payload_sha256": digest(trace.model_dump()),
        },
    )


def load_trace(path: Path) -> Trace:
    data = json.loads(path.read_text())
    if data.get("schema_version") != 1 or digest(data["trace"]) != data["payload_sha256"]:
        raise RecordingMismatch(f"Recording hash/schema mismatch: {path.name}")
    return Trace.model_validate(data["trace"])


def strict_replay(path: Path, expected_hash: str) -> Trace:
    if __import__("hashlib").sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise RecordingMismatch("Recording does not match trusted baseline manifest")
    original = load_trace(path)
    # Preserve original timestamps, usage, and latency; caller records playback time separately.
    return original.model_copy(update={"mode": "replay"})
