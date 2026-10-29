"""Local OpenTelemetry spans with an allowlisted JSON log export; no network sink."""

import logging
from typing import Any

from opentelemetry.context import Context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    get_current_span,
    set_span_in_context,
)

from ..util import canonical

log = logging.getLogger(__name__)
ALLOWED = frozenset(
    {"request_id", "job_id", "attempt", "worker_id", "route", "status", "accepted", "ok"}
)


class LogExporter(SpanExporter):
    def export(self, spans: Any) -> SpanExportResult:
        for span in spans:
            log.info(
                canonical(
                    {
                        "event": "workflow_span",
                        "name": span.name,
                        "trace_id": f"{span.context.trace_id:032x}",
                        "span_id": f"{span.context.span_id:016x}",
                        "parent_span_id": f"{span.parent.span_id:016x}" if span.parent else None,
                        "duration_ms": (span.end_time - span.start_time) / 1_000_000,
                        "attributes": {
                            k: v for k, v in (span.attributes or {}).items() if k in ALLOWED
                        },
                    }
                )
            )
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


class Telemetry:
    def __init__(self) -> None:
        self.provider = TracerProvider(sampler=ALWAYS_ON)
        self.provider.add_span_processor(SimpleSpanProcessor(LogExporter()))
        self.tracer = self.provider.get_tracer("arh.workflow", "stage5")

    def span(
        self,
        name: str,
        *,
        trace_id: str | None = None,
        parent_span_id: str | None = None,
        **attributes: Any,
    ) -> Any:
        context = Context()
        if trace_id and parent_span_id:
            parent = SpanContext(int(trace_id, 16), int(parent_span_id, 16), True, TraceFlags(1))
            context = set_span_in_context(NonRecordingSpan(parent), context)
        return self.tracer.start_as_current_span(
            name,
            context=context,
            attributes={k: v for k, v in attributes.items() if k in ALLOWED and v is not None},
            record_exception=False,
            set_status_on_exception=False,
        )

    def close(self) -> None:
        self.provider.shutdown()


def carrier() -> tuple[str | None, str | None]:
    context = get_current_span().get_span_context()
    if not context.is_valid:
        return None, None
    return f"{context.trace_id:032x}", f"{context.span_id:016x}"


def prometheus(values: dict[str, Any]) -> str:
    lines = []
    for family, states in {
        "jobs": (
            "queued",
            "waiting_approval",
            "running",
            "retry_wait",
            "succeeded",
            "failed",
            "cancelled",
        ),
        "attempts": ("running", "succeeded", "failed", "timed_out", "lost", "cancelled"),
        "operations": ("reserved", "in_flight", "succeeded", "uncertain", "released"),
    }.items():
        name = "arh_workflow_" + family
        lines.append(f"# TYPE {name} gauge")
        lines += [
            f'{name}{{state="{state}"}} {int(values[family].get(state, 0))}' for state in states
        ]
    for key in ("queue_age_seconds", "stale_result_rejections"):
        lines += [f"# TYPE arh_workflow_{key} gauge", f"arh_workflow_{key} {values[key]}"]
    budget = values["budget"]
    lines.append(f"arh_workflow_budget_configured {int(budget is not None)}")
    if budget is not None:
        lines += [
            f"arh_workflow_budget_{key} {int(budget[key])}"
            for key in ("limit_units", "reserved_units", "spent_units")
        ]
    return "\n".join(lines) + "\n"
