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
)


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
