import csv
from collections import Counter
from pathlib import Path
from typing import Any

LABELS = [
    "wrong_tool",
    "bad_arguments",
    "hallucinated_schema",
    "loop",
    "unsafe_action",
    "wrong_answer_valid_sql",
    "budget_exceeded",
    "unknown",
]


def blinded_export(
    rows: list[dict[str, Any]], destination: Path, excluded_attempts: set[str] | None = None
) -> int:
    excluded = excluded_attempts or set()
    eligible = [
        r
        for r in rows
        if r.get("origin") == "live"
        and r.get("mode") == "record"
        and r.get("split") == "dev"
        and not r.get("correct")
        and r["attempt_id"] not in excluded
    ]
    distinct = {r["attempt_id"]: r for r in eligible}
    selected = sorted(distinct.values(), key=lambda r: r["attempt_id"])[:50]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "attempt_id",
                "trace_path",
                "human_label",
                "reviewer",
                "ambiguity",
                "adjudication",
            ],
        )
        writer.writeheader()
        for row in selected:
            writer.writerow({"attempt_id": row["attempt_id"], "trace_path": row["trace_path"]})
    return len(selected)


def agreement(predicted: list[str], human: list[str]) -> dict[str, Any]:
    if len(predicted) != len(human) or not predicted:
        raise ValueError("Matched nonempty actual human labels are required")
    if any(x not in LABELS for x in predicted + human):
        raise ValueError("Unknown taxonomy label")
    n = len(human)
    accuracy = sum(a == b for a, b in zip(predicted, human, strict=True)) / n
    p, h = Counter(predicted), Counter(human)
    chance = sum(p[k] * h[k] for k in LABELS) / (n * n)
    confusion = {
        actual: {
            guess: sum(a == actual and b == guess for a, b in zip(human, predicted, strict=True))
            for guess in LABELS
        }
        for actual in LABELS
    }
    return {
        "n": n,
        "accuracy": accuracy,
        "cohens_kappa": (accuracy - chance) / (1 - chance) if chance < 1 else None,
        "confusion_matrix_actual_rows": confusion,
        "human_category_counts": dict(h),
        "interpretation": "classifier-versus-human agreement; not inter-human agreement",
    }
