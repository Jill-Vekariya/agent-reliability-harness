import json
import socket

import pytest

from agent_reliability.agents import SQLAgent
from agent_reliability.models import TaskInput
from agent_reliability.providers.fixture import FixtureProvider
from agent_reliability.tracing.recording import (
    RecordedProvider,
    RecordingMismatch,
    load_trace,
    save_trace,
    strict_replay,
)
from agent_reliability.util import digest


def test_regression_current_tools_and_no_network(sandbox, tmp_path, monkeypatch):
    script = [
        {"name": "run_sql", "arguments": {"sql": "SELECT 1"}},
        {"name": "final_answer", "arguments": {"status": "answered", "result_id": "r001"}},
    ]
    task = TaskInput(id="opaque", question="Return one.")
    original = SQLAgent(FixtureProvider(script), sandbox).run(task)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Network forbidden")),
    )
    called = []
    real = sandbox.run
    monkeypatch.setattr(sandbox, "run", lambda sql: (called.append(sql), real(sql))[1])
    fresh = SQLAgent(RecordedProvider(original), sandbox, mode="regression").run(task)
    assert called == ["SELECT 1"] and fresh.final == original.final
    changed = SQLAgent(RecordedProvider(original), sandbox, mode="regression").run(
        TaskInput(id="opaque", question="Changed question.")
    )
    assert changed.infrastructure_error and "RecordingMismatch" in changed.infrastructure_error
    path = tmp_path / "trace.json"
    save_trace(path, original)
    data = json.loads(path.read_text())
    data["trace"]["task_id"] = "tampered"
    path.write_text(json.dumps(data))
    with pytest.raises(RecordingMismatch):
        load_trace(path)


def test_no_gold_in_serialized_request(sandbox):
    from agent_reliability.models import EvaluationTask

    task = EvaluationTask(
        id="q",
        question="How many artists?",
        difficulty="easy",
        category="ordinary",
        family_id="count",
        gold_sql="SELECT COUNT(*) FROM Artist",
        expected_result=[[275]],
        expected_columns=["n"],
    )
    trace = SQLAgent(
        FixtureProvider(
            [
                {
                    "name": "final_answer",
                    "arguments": {"status": "needs_clarification", "result_id": None},
                }
            ]
        ),
        sandbox,
    ).run(task.agent_input())
    request = json.dumps(trace.events[0].payload["request"])
    for secret in [
        "SELECT COUNT(*) FROM Artist",
        "expected_result",
        "gold_sql",
        "family_id",
        '"dev"',
    ]:
        assert secret not in request


@pytest.mark.parametrize(
    "kind",
    [
        "root",
        "missing_hash",
        "inner_version",
        "event_version",
        "indices",
        "payload",
        "duplicate_key",
        "missing_events",
        "boolean_version",
    ],
)
def test_malformed_recordings_are_domain_errors(sandbox, tmp_path, kind):
    trace = SQLAgent(FixtureProvider([{"name": "list_tables", "arguments": {}}]), sandbox).run(
        TaskInput(id="opaque", question="List tables")
    )
    path = tmp_path / "bad.json"
    save_trace(path, trace)
    envelope = json.loads(path.read_text())
    if kind == "root":
        envelope = []
    elif kind == "missing_hash":
        del envelope["payload_sha256"]
    else:
        if kind == "inner_version":
            envelope["trace"]["schema_version"] = 2
        elif kind == "event_version":
            envelope["trace"]["events"][0]["schema_version"] = 2
        elif kind == "indices":
            envelope["trace"]["events"][0]["index"] = 7
        elif kind == "payload":
            envelope["trace"]["events"][0]["payload"] = {}
        elif kind == "missing_events":
            del envelope["trace"]["events"]
        elif kind == "boolean_version":
            envelope["trace"]["schema_version"] = True
        envelope["payload_sha256"] = digest(envelope["trace"])
    text = json.dumps(envelope)
    if kind == "duplicate_key":
        text = text.replace('"schema_version": 1', '"schema_version": 2, "schema_version": 1', 1)
    path.write_text(text)
    with pytest.raises(RecordingMismatch):
        load_trace(path)


def test_trusted_file_hash_rejects_rehashed_payload(sandbox, tmp_path):
    from agent_reliability.util import file_hash

    path = tmp_path / "signed-by-manifest.json"
    trace = SQLAgent(FixtureProvider([]), sandbox).run(TaskInput(id="q", question="Example"))
    save_trace(path, trace)
    trusted = file_hash(path)
    save_trace(path, trace.model_copy(update={"task_id": "changed"}))
    with pytest.raises(RecordingMismatch):
        strict_replay(path, trusted)


def test_trace_size_limit_applies_before_json_and_trusted_replay(tmp_path, monkeypatch):
    import agent_reliability.tracing.recording as recording

    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * 1024)
    with pytest.raises(RecordingMismatch, match="byte limit"):
        load_trace(path, max_bytes=100)
    # Prove strict replay uses the bounded loader rather than a separate read_bytes.
    monkeypatch.setattr(type(path), "read_bytes", lambda self: pytest.fail("unbounded read"))
    with pytest.raises(RecordingMismatch, match="trusted baseline"):
        recording.strict_replay(path, "0" * 64)
