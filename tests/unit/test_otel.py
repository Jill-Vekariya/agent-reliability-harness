import json

from agent_reliability.models import Event, Trace
from agent_reliability.tracing.otel import export_trace


def test_actual_sdk_span_relationships(tmp_path):
    path = tmp_path / "otel.jsonl"
    trace = Trace(
        task_id="t",
        attempt_id="a",
        mode="fixture",
        origin="synthetic",
        config="x",
        events=[
            Event(
                index=0,
                kind="termination",
                payload={"reason": "test"},
                timestamp="2026-10-18T00:00:00Z",
            )
        ],
    )
    export_trace(trace, path)
    spans = [json.loads(line) for line in path.read_text().splitlines()]
    child, parent = spans
    assert child["parent_id"] == parent["context"]["span_id"]
    assert child["context"]["trace_id"] == parent["context"]["trace_id"]
