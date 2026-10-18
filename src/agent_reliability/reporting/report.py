import csv
from collections import Counter
from pathlib import Path
from typing import Any

from ..evaluation.statistics import live_metrics
from ..util import write_json


def build_report(summary: dict[str, Any], destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    rows = summary["rows"]
    metrics = live_metrics(rows)
    write_json(destination / "metrics.json", metrics)
    if rows:
        with (destination / "attempts.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    failures = Counter(r["failure_category"] for r in rows if r["failure_category"])
    ordinary = [r for r in rows if r["category"] == "ordinary"]
    lines = [
        "# Study protocol — live results not yet measured",
        "",
        f"Fresh ordinary model attempts: {metrics['fresh_ordinary_attempts']}.",
        "",
        "These bundled engineering runs use prewritten synthetic responses. They are not model benchmarks, human reviews, or paid evaluations.",
        "",
        "| Engineering fixture check | Count |",
        "|---|---:|",
        f"| Ordinary scripted cases executed | {len(ordinary)} |",
        f"| Ordinary scripted result matches | {sum(r['correct'] for r in ordinary)} |",
        f"| Safety/clarification diagnostic cases | {len(rows) - len(ordinary)} |",
        f"| Prohibited operations executed | {sum(r['prohibited_executed'] for r in rows)} |",
        "| Paid API spend | USD 0 |",
        "",
        "## Headline results",
        "",
        "Pass@1, pass@5, model flakiness, Pareto frontier, paired ablation effects, live safety rates, and human-classifier agreement: **not yet measured**.",
        "",
        "No Pareto chart is generated from synthetic fixtures.",
        "",
        "## Synthetic detector outcomes",
        "",
        "| Detector label | Cases |",
        "|---|---:|",
    ]
    lines.extend(f"| {name} | {n} |" for name, n in sorted(failures.items()))
    lines.extend(
        ["", "## Trace index", "", "| Task | Mode | Outcome | Trace |", "|---|---|---|---|"]
    )
    lines.extend(
        f"| {r['task_id']} | {r['mode']} / {r['origin']} | {r['reason']} | {r['trace_path']} |"
        for r in rows
    )
    (destination / "REPORT.md").write_text("\n".join(lines) + "\n")
    return destination / "REPORT.md"
