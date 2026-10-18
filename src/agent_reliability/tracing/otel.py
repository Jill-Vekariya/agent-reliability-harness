"""Tested core OpenTelemetry mapping, not a claim of GenAI convention compliance."""

import json
from pathlib import Path
from typing import Any

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import Status, StatusCode

from ..models import Trace


class JSONLExporter(SpanExporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def export(self, spans: Any) -> SpanExportResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as stream:
            for span in spans:
                stream.write(json.dumps(json.loads(span.to_json()), separators=(",", ":")) + "\n")
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


def export_trace(trace: Trace, path: Path) -> None:
    # An archival export must not drop spans because of the caller's sampling environment.
    provider = TracerProvider(sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(JSONLExporter(path)))
    tracer = provider.get_tracer("agent_reliability", "0.1.0")
    with tracer.start_as_current_span(
        "agent.attempt",
        attributes={
            "arh.task_id": trace.task_id,
            "arh.mode": trace.mode,
            "arh.origin": trace.origin,
        },
    ):
        for event in trace.events:
            with tracer.start_as_current_span(
                "agent." + event.kind,
                attributes={
                    "arh.event_index": event.index,
                    "arh.source_timestamp": event.timestamp,
                    "arh.original_latency_ms": event.latency_ms,
                },
            ) as span:
                if event.kind == "tool" and event.payload["output"].get("error"):
                    span.set_status(Status(StatusCode.ERROR, str(event.payload["output"]["error"])))
    provider.shutdown()
