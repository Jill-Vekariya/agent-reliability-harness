"""Offline dataset integrity and paired regression gates."""

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def validate_dataset(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Reject ID, normalized-question and family leakage across dev/test."""
    if not rows:
        raise ValueError("Dataset must not be empty")
    ids: set[str] = set()
    owners: dict[tuple[str, str], str] = {}
    counts = {"dev": 0, "test": 0}
    for row in rows:
        task_id = _text(row, "id")
        if task_id in ids:
            raise ValueError(f"Duplicate task ID: {task_id}")
        ids.add(task_id)
        split = _text(row, "split")
        if split not in counts:
            raise ValueError(f"Invalid split: {split}")
        counts[split] += 1
        question = " ".join(_text(row, "question").casefold().split())
        family = _text(row, "family_id")
        for key in (("question", question), ("family", family)):
            if key in owners and owners[key] != split:
                raise ValueError(f"Cross-split {key[0]} overlap at {task_id}")
            owners[key] = split
        status = row.get("review_status", "candidate")
        if status not in {"candidate", "human_reviewed"}:
            raise ValueError(f"Invalid review_status at {task_id}")
        if status == "human_reviewed":
            _text(row, "reviewer")
    return {"schema_version": 1, "tasks": len(ids), "splits": counts}


def _number(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return float(value)


def _index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not rows:
        raise ValueError("Run must not be empty")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        task_id = _text(row, "task_id")
        if task_id in result:
            raise ValueError(f"Duplicate task_id: {task_id}")
        if type(row.get("passed")) is not bool:
            raise ValueError("passed must be a boolean")
        for key in ("latency_ms", "cost_usd"):
            if row.get(key) is not None:
                _number(row[key], key)
        result[task_id] = row
    return result


def compare_runs(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    max_drop: float = 0.0,
) -> dict[str, Any]:
    """Compare paired tasks; max_drop is an absolute rate, not percent."""
    _number(max_drop, "max_drop")
    if max_drop > 1:
        raise ValueError("max_drop must be between 0 and 1")
    before, after = _index(baseline), _index(candidate)
    if before.keys() != after.keys():
        raise ValueError("Task sets differ; refusing an unpaired comparison")
    count = len(before)
    base_passes = sum(row["passed"] for row in before.values())
    next_passes = sum(row["passed"] for row in after.values())
    regressions = sorted(
        key for key in before if before[key]["passed"] and not after[key]["passed"]
    )
    improvements = sorted(
        key for key in before if not before[key]["passed"] and after[key]["passed"]
    )
    metrics: dict[str, Any] = {}
    for key in ("latency_ms", "cost_usd"):
        complete = all(row.get(key) is not None for row in [*before.values(), *after.values()])
        if complete:
            old = math.fsum(float(row[key]) for row in before.values())
            new = math.fsum(float(row[key]) for row in after.values())
            metrics[key] = {"baseline_total": old, "candidate_total": new, "delta": new - old}
        else:
            metrics[key] = None
    return {
        "schema_version": 1,
        "tasks": count,
        "baseline_pass_rate": base_passes / count,
        "candidate_pass_rate": next_passes / count,
        "pass_rate_delta": (next_passes - base_passes) / count,
        "regressions": regressions,
        "improvements": improvements,
        "metrics": metrics,
        "gate_passed": (base_passes - next_passes) / count <= max_drop,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dataset = commands.add_parser("dataset")
    dataset.add_argument("input", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--max-drop", type=float, default=0.0)
    args = parser.parse_args()

    def load(path: Path) -> list[dict[str, Any]]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ValueError("Expected a JSON array of objects")
        return value

    try:
        if args.command == "dataset":
            result = validate_dataset(load(args.input))
        else:
            result = compare_runs(load(args.baseline), load(args.candidate), args.max_drop)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        parser.exit(2, f"quality: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result.get("gate_passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
