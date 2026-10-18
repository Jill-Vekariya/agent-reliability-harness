import hashlib
import json
from pathlib import Path
from typing import Any

from ..models import ProviderReply, Trace
from ..util import digest, write_json


class RecordingMismatch(RuntimeError):
    pass


MAX_TRACE_BYTES = 16 * 1024 * 1024


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _schema_version(value: Any) -> bool:
    return type(value) is int and value == 1


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


def load_trace(
    path: Path, *, max_bytes: int = MAX_TRACE_BYTES, expected_hash: str | None = None
) -> Trace:
    try:
        if max_bytes < 1 or path.stat().st_size > max_bytes:
            raise ValueError("Trace exceeds byte limit")
        with path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Trace exceeds byte limit")
        if expected_hash is not None and hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("Recording does not match trusted baseline manifest")
        data = json.loads(raw, object_pairs_hook=_unique_object)
        if not isinstance(data, dict) or set(data) != {"schema_version", "trace", "payload_sha256"}:
            raise ValueError("Invalid envelope fields")
        if not _schema_version(data["schema_version"]) or not isinstance(data["trace"], dict):
            raise ValueError("Unsupported envelope version or payload")
        payload = data["trace"]
        if set(payload) != set(Trace.model_fields):
            raise ValueError("Missing or unexpected trace fields")
        if not _schema_version(payload.get("schema_version")):
            raise ValueError("Unsupported trace version")
        if digest(payload) != data["payload_sha256"]:
            raise ValueError("Trace payload checksum mismatch")
        trace = Trace.model_validate(payload)
        for index, event in enumerate(trace.events):
            if (
                not _schema_version(payload["events"][index].get("schema_version"))
                or event.index != index
            ):
                raise ValueError("Unsupported event version or non-contiguous index")
            if event.kind == "model":
                if not isinstance(event.payload.get("request"), dict):
                    raise ValueError("Missing normalized model request")
                ProviderReply.model_validate(event.payload["response"])
            elif event.kind == "tool":
                if not (
                    isinstance(event.payload.get("name"), str)
                    and isinstance(event.payload.get("arguments"), dict)
                    and isinstance(event.payload.get("output"), dict)
                ):
                    raise ValueError("Malformed tool event")
            elif not isinstance(event.payload.get("reason"), str):
                raise ValueError("Malformed termination event")
        return trace
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise RecordingMismatch(f"Invalid recording {path.name}: {str(exc)[:250]}") from exc


def strict_replay(path: Path, expected_hash: str) -> Trace:
    # Check the hash and parse the same bounded byte snapshot, avoiding both an
    # unbounded pre-validation read and a hash/read race.
    original = load_trace(path, expected_hash=expected_hash)
    # Preserve original timestamps, usage, and latency; caller records playback time separately.
    return original.model_copy(update={"mode": "replay"})
