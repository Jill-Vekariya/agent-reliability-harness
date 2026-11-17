"""Payload-free trace health reports and operational budget checks."""

import argparse
import json
import math
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _cost(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("cost_usd must be decimal text")
    try:
        cost = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid cost_usd") from exc
    if not cost.is_finite() or cost < 0:
        raise ValueError("cost_usd must be finite and non-negative")
    return cost


def _latency(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("latency_ms must be numeric")
    latency = float(value)
    if not math.isfinite(latency) or latency < 0:
        raise ValueError("latency_ms must be finite and non-negative")
    return latency


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize selected v1 fields without exposing questions, SQL or rows."""
    if not traces:
        raise ValueError("At least one trace is required")
    seen: set[tuple[str, str]] = set()
    terminations: Counter[str] = Counter()
    latencies: list[float] = []
    costs: list[Decimal] = []
    results = failures = blocked = limited = truncated = infrastructure = 0
    for trace in traces:
        if type(trace.get("schema_version")) is not int or trace["schema_version"] != 1:
            raise ValueError("Expected trace schema_version 1")
        for key in ("task_id", "attempt_id", "termination"):
            if not isinstance(trace.get(key), str) or not trace[key].strip():
                raise ValueError(f"{key} must be non-empty text")
        identity = (trace["task_id"], trace["attempt_id"])
        if identity in seen:
            raise ValueError("Duplicate task/attempt pair")
        seen.add(identity)
        latencies.append(_latency(trace.get("latency_ms")))
        terminations[trace["termination"]] += 1
        error = trace.get("infrastructure_error")
        if error is not None and not isinstance(error, str):
            raise ValueError("infrastructure_error must be text or null")
        infrastructure += error is not None
        if trace.get("cost_usd") is not None:
            costs.append(_cost(trace["cost_usd"]))
        sql_results = trace.get("results", {})
        if not isinstance(sql_results, dict):
            raise ValueError("results must be an object")
        for result in sql_results.values():
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                raise ValueError("Each SQL result needs a boolean ok field")
            for key in ("blocked", "resource_limited", "truncated"):
                if type(result.get(key, False)) is not bool:
                    raise ValueError(f"{key} must be boolean")
            results += 1
            failures += not result["ok"]
            blocked += result.get("blocked", False)
            limited += result.get("resource_limited", False)
            truncated += result.get("truncated", False)
    latencies.sort()
    return {
        "schema_version": 1,
        "traces": len(traces),
        "terminations": dict(sorted(terminations.items())),
        "infrastructure_errors": infrastructure,
        "sql_results": results,
        "sql_failures": failures,
        "blocked_results": blocked,
        "resource_limited_results": limited,
        "truncated_results": truncated,
        "latency_ms": {
            "p50": latencies[math.ceil(len(latencies) * 0.5) - 1],
            "p95": latencies[math.ceil(len(latencies) * 0.95) - 1],
            "max": latencies[-1],
        },
        "cost_usd": str(sum(costs, Decimal(0))) if len(costs) == len(traces) else None,
        "traces_with_known_cost": len(costs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path, help="Individual trace JSON files")
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument("--max-cost-usd")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    try:
        if args.max_p95_ms is not None and (
            not math.isfinite(args.max_p95_ms) or args.max_p95_ms < 0
        ):
            raise ValueError("--max-p95-ms must be finite and non-negative")
        budget = _cost(args.max_cost_usd) if args.max_cost_usd is not None else None
        traces = [json.loads(path.read_text(encoding="utf-8")) for path in args.traces]
        if not all(isinstance(trace, dict) for trace in traces):
            raise ValueError("Each input must be a trace object")
        report = summarize(traces)
        violations: list[str] = []
        if args.max_p95_ms is not None and report["latency_ms"]["p95"] > args.max_p95_ms:
            violations.append("p95_latency_exceeded")
        if budget is not None:
            if report["cost_usd"] is None:
                violations.append("cost_unknown")
            elif _cost(report["cost_usd"]) > budget:
                violations.append("cost_budget_exceeded")
        if args.fail_on_error and (report["sql_failures"] or report["infrastructure_errors"]):
            violations.append("recorded_errors")
        report["violations"] = violations
        report["gate_passed"] = not violations
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.exit(2, f"diagnostics: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
