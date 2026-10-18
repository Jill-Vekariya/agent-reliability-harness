import csv
import os
from collections import Counter
from pathlib import Path
from typing import Any

from ..evaluation.statistics import live_metrics, paired_difference
from ..util import write_json


def build_report(
    summary: dict[str, Any], destination: Path, trace_base: Path | None = None
) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    # These are generated outputs, not user inputs. Remove previous measurements
    # before rendering a partial/replay report into a reused destination.
    for name in ("pareto.png", "paired-effects.json", "attempts.csv"):
        (destination / name).unlink(missing_ok=True)
    rows = summary["rows"]
    fresh = [r for r in rows if r["origin"] == "live" and r["mode"] == "record"]
    if len({r["attempt_id"] for r in fresh}) != len(fresh):
        raise ValueError("Duplicate fresh attempts cannot be counted as evidence")
    if len({row.get("split") for row in fresh}) > 1:
        raise ValueError("Report development and held-out results separately")
    planned = summary.get("planned_attempts")
    metrics = (
        {
            "status": "stratified; consult configuration coverage",
            "fresh_ordinary_attempts": sum(row["category"] == "ordinary" for row in fresh),
        }
        if fresh
        else live_metrics(rows)
    )
    names = {r["config"] for r in fresh} | {r["config"] for r in (planned or [])}
    groups = {name: [r for r in fresh if r["config"] == name] for name in sorted(names)}
    by_config = {
        name: live_metrics(
            group,
            planned_attempts=None
            if planned is None
            else [row for row in planned if row["config"] == name],
            require_manifest=True,
        )
        for name, group in groups.items()
    }
    metrics["by_configuration"] = by_config
    write_json(destination / "metrics.json", metrics)
    if rows:
        with (destination / "attempts.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=sorted({k for row in rows for k in row}))
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
    if not fresh and planned is None and any(row["origin"] == "live" for row in rows):
        lines = [
            "# Saved live traces — playback only",
            "",
            f"Saved outcomes: {len(rows)}. Fresh recorded attempts: 0.",
            "",
            "Replay/regression is not a fresh model measurement. Original provider cost is historical; this report makes no claim about paid spend or headline performance.",
        ]
    if fresh or planned is not None:
        lines = [
            f"# What {len(fresh)} agent runs taught me about failure modes"
            if fresh
            else "# Campaign coverage — no completed model outcomes",
            "",
            "N counts unique fresh recorded attempts in this report, including safety cases. Synthetic, replay, and regression rows are excluded.",
            "Scope: "
            + ", ".join(sorted({row["split"] for row in fresh + (planned or [])}))
            + ". Development measurements do not establish held-out performance.",
            "Ledger exposure (if supplied): "
            + str(summary.get("ledger", "not supplied; no zero-cost assumption")),
            "",
            "| Configuration | Ordinary attempts | Pass@1 | 95% interval | Pass@5 | Mean USD/attempt | p50/p95 ms |",
            "|---|---:|---:|---|---:|---:|---|",
        ]
        for name, m in by_config.items():
            lines.append(
                f"| {name} | {m['fresh_ordinary_attempts']} | {m.get('pass_at_1')} | {m.get('pass_at_1_ci95')} | {m.get('pass_at_5')} | {m.get('mean_cost_usd')} | {m.get('latency_p50_ms')}/{m.get('latency_p95_ms')} |"
            )
        lines += [
            "",
            "Undefined values indicate insufficient coverage/usage, not zero. Intervals resample whole families; few-family/degenerate intervals provide limited evidence. Pass@5 assumes an oracle.",
            "Headline pass/cost metrics require complete declared campaign coverage. Started or never-started gaps are retained separately; observed latency and success intervals describe only recorded outcomes.",
            "",
            "## Paired configuration contrasts",
            "",
        ]
        for name, measurement in by_config.items():
            lines.append(
                f"* {name}: {measurement['fresh_ordinary_attempts']} observed ordinary outcomes; planned={measurement.get('planned_ordinary_attempts')}; missing={measurement.get('missing_expected_attempts')}; status={measurement['status']}."
            )
        effects = {}
        if "B" in groups:
            reference = [r for r in groups["B"] if r["category"] == "ordinary"]
            for name, group in groups.items():
                if name == "B":
                    continue
                if (
                    by_config["B"]["status"] != "measured"
                    or by_config[name]["status"] != "measured"
                ):
                    lines.append(
                        f"* {name} versus B: complete planned coverage unavailable; no paired effect estimated."
                    )
                    continue
                try:
                    effect = paired_difference(
                        reference, [r for r in group if r["category"] == "ordinary"]
                    )
                    effects[name] = effect
                    lines.append(
                        f"* {name} minus B: {effect['effect']:.4f}, 95% interval {effect['ci95']}."
                    )
                except ValueError:
                    lines.append(
                        f"* {name} versus B: incompatible/missing coverage; no paired effect estimated."
                    )
        else:
            lines.append("No full-B comparator in the supplied artifacts; paired effects pending.")
        write_json(destination / "paired-effects.json", effects)
        points = [
            (name, m)
            for name, m in by_config.items()
            if m.get("pass_at_1") is not None and m.get("mean_cost_usd") is not None
        ]
        if points:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(7, 4))
            for name, m in points:
                x, y = m["mean_cost_usd"], m["pass_at_1"]
                ylow, yhigh = m["pass_at_1_ci95"]
                xlow, xhigh = m["mean_cost_ci95_usd"]
                ax.errorbar(
                    [x],
                    [y],
                    xerr=[[max(0, x - xlow)], [max(0, xhigh - x)]],
                    yerr=[[max(0, y - ylow)], [max(0, yhigh - y)]],
                    fmt="o",
                    capsize=3,
                )
                ax.annotate(name, (x, y), xytext=(5, 5), textcoords="offset points")
            ax.set(
                xlabel="Measured mean API USD per ordinary attempt",
                ylabel="Measured ordinary pass@1",
                ylim=(-0.03, 1.03),
            )
            fig.tight_layout()
            fig.savefig(destination / "pareto.png", dpi=160)
            plt.close(fig)
            lines += [
                "",
                "![Measured cost/reliability comparison](pareto.png)",
                "",
                "Uncertainty may prevent a confident ordering of the Pareto frontier.",
            ]
        lines += [
            "",
            "## Safety and failure analysis",
            "",
            f"Unsafe proposal attempts: {sum(r.get('unsafe_attempt', False) for r in fresh)}/{len(fresh)}.",
            f"Executed prohibited-action attempts: {sum(r.get('prohibited_executed', False) for r in fresh)}/{len(fresh)}.",
            "Call-level conditional block rates and injection-conditional analyses require their trace evidence and declared exposure denominators; a missing denominator is not a 100% block rate.",
            "Classifier-versus-human agreement remains pending until actual held-out labels are imported. Non-obvious relationships must be investigated against these traces before claiming a finding.",
        ]
        if all(
            "unsafe_sql_proposals" in row and "blocked_unsafe_sql_proposals" in row for row in fresh
        ):
            proposed = sum(row["unsafe_sql_proposals"] for row in fresh)
            blocked = sum(row["blocked_unsafe_sql_proposals"] for row in fresh)
            lines.append(
                f"Heuristically detected unsafe SQL calls blocked: {blocked}/{proposed}; conditional rate={blocked / proposed if proposed else 'undefined (zero proposals)'}."
            )
        injected = [
            row
            for row in fresh
            if row.get("category") == "injection" and row.get("injection_exposed") is True
        ]
        lines.append(
            f"Unsafe decisions among injection-exposed attempts: {sum(bool(row.get('unsafe_attempt')) for row in injected)}/{len(injected)}; conditional rate={sum(bool(row.get('unsafe_attempt')) for row in injected) / len(injected) if injected else 'undefined (no recorded exposure)'}."
        )
    lines.extend(
        ["", "## Trace index", "", "| Task | Mode | Outcome | Trace |", "|---|---|---|---|"]
    )
    lines.extend(
        f"| {r['task_id']} | {r['mode']} / {r['origin']} | {r['reason']} | [trace]({os.path.relpath((trace_base or destination) / r['trace_path'], destination)}) |"
        for r in rows
    )
    (destination / "REPORT.md").write_text("\n".join(lines) + "\n")
    return destination / "REPORT.md"
