import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from .evaluation.human import blinded_export
from .evaluation.tasks import lint_tasks, load_tasks
from .reporting.report import build_report
from .runner import run_offline
from .util import file_hash


def project_root() -> Path:
    configured = os.environ.get("ARH_PROJECT_ROOT")
    return Path(configured) if configured else Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Reliability Harness — USD 0, offline by default"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("eval")
    evaluate.add_argument(
        "--mode", choices=["fixture", "regression", "replay"], default="regression"
    )
    evaluate.add_argument("--all", action="store_true")
    evaluate.add_argument("--resume", type=Path)
    sub.add_parser("data")
    sub.add_parser("validate-tasks")
    sub.add_parser("estimate")
    report = sub.add_parser("report")
    report.add_argument("--summary", type=Path)
    report.add_argument("--output", type=Path)
    live = sub.add_parser("eval-live")
    live.add_argument("--config", type=Path, required=True)
    live.add_argument("--approval", type=Path, required=True)
    live.add_argument("--split", choices=["dev", "test"], default="dev")
    live.add_argument("--repetitions", type=int, default=5)
    live.add_argument("--resume", type=Path)
    human = sub.add_parser("label-export")
    human.add_argument("--summary", type=Path, required=True)
    human.add_argument("--output", type=Path, required=True)
    human.add_argument(
        "--exclude",
        type=Path,
        required=True,
        help="JSON list of dev traces used to design classifier",
    )
    review_export = sub.add_parser(
        "review-export", help="Export a blank, provenance-bound benchmark review packet"
    )
    review_export.add_argument("--output", type=Path, required=True)
    review_check = sub.add_parser(
        "review-check", help="Validate review attestations without modifying task metadata"
    )
    review_check.add_argument("--packet", type=Path, required=True)
    review_check.add_argument("--require-complete", action="store_true")
    split_plan = sub.add_parser(
        "split-plan", help="Draft groups while preserving development exposure history"
    )
    split_plan.add_argument("--output", type=Path, required=True)
    split_plan.add_argument("--seed", type=int, default=20261018)
    split_check = sub.add_parser("split-check")
    split_check.add_argument("--manifest", type=Path, required=True)
    from .workflow.cli import add_commands

    add_commands(sub)
    args = parser.parse_args()
    root = project_root()
    try:
        if args.command == "jobs":
            from .workflow.cli import run

            run(args, root)
        elif args.command == "data":
            manifest = json.loads((root / "data/manifest.json").read_text())
            if file_hash(root / "data/chinook.sqlite") != manifest["database_sha256"]:
                raise ValueError("Bundled Chinook checksum mismatch; restore verified snapshot")
            for fixture in manifest.get("fixtures", {}).values():
                if file_hash(root / fixture["path"]) != fixture["sha256"]:
                    raise ValueError("Bundled diagnostic fixture checksum mismatch")
            print(
                "Pinned Chinook v1.4.5 and diagnostic fixture checksums verified; no download needed."
            )
        elif args.command == "validate-tasks":
            errors = lint_tasks(root)
            print(
                json.dumps(
                    {
                        "tasks": len(load_tasks(root)),
                        "errors": errors,
                        "human_reviewed": sum(
                            t.review_status == "human_reviewed" for t in load_tasks(root)
                        ),
                    },
                    indent=2,
                )
            )
            if errors:
                sys.exit(1)
        elif args.command == "eval":
            print(f"MODE={args.mode}; network/model fallback forbidden; bundled origin=SYNTHETIC")
            result = run_offline(
                root,
                mode=args.mode,
                all_tasks=args.all,
                resume=args.resume,
                artifact_root=Path(os.environ.get("ARH_ARTIFACT_DIR", str(root / "artifacts"))),
            )
            print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))
            if not result["gate_passed"]:
                sys.exit(1)
        elif args.command == "estimate":
            tasks = load_tasks(root)
            output = {
                "currency": "USD",
                "authorized_budget": "0",
                "pricing_status": "unknown / unconfigured; paid execution disabled",
                "current_dev_candidates": sum(t.split == "dev" for t in tasks),
                "current_reviewed_test_tasks": sum(
                    t.split == "test" and t.review_status == "human_reviewed" for t in tasks
                ),
                "target_test_tasks": 60,
                "target_configurations": 7,
                "fresh_repetitions": 5,
                "target_test_agent_attempts": 2100,
                "target_ordinary_attempts": 1680,
                "target_safety_attempts": 420,
                "cost_upper_bound_usd": None,
                "pilot_cost_usd": None,
                "full_study_cost_usd": None,
                "note": "Planning arithmetic only. Supply verified official model/pricing/context bounds and request concrete approval before paid work.",
            }
            print(json.dumps(output, indent=2))
        elif args.command == "report":
            summary_path = args.summary or root / "demo/summary.json"
            summary = json.loads(summary_path.read_text())
            destination = args.output or root / "reports/generated"
            print(build_report(summary, destination, trace_base=summary_path.parent))
        elif args.command == "label-export":
            rows = json.loads(args.summary.read_text())["rows"]
            excluded = set(json.loads(args.exclude.read_text()))
            count = blinded_export(rows, args.output, excluded)
            print(f"Exported {count}/50 eligible genuine dev failures. Human labels pending.")
        elif args.command == "review-export":
            from .evaluation.review import export_review

            export_review(root, args.output)
            print(f"Blank candidate review packet: {args.output}. No tasks marked reviewed.")
        elif args.command == "review-check":
            from .evaluation.review import check_reviews

            result = check_reviews(root, json.loads(args.packet.read_text()))
            print(json.dumps(result, indent=2))
            if result["errors"] or (
                args.require_complete and not result["ready_for_metadata_review"]
            ):
                sys.exit(1)
        elif args.command == "split-plan":
            from .evaluation.review import grouped_split
            from .util import write_json

            if args.output.exists():
                raise ValueError("Split proposal already exists; preserve prior review")
            result = grouped_split(root, seed=args.seed)
            write_json(args.output, result)
            print(
                json.dumps(
                    {
                        key: result[key]
                        for key in ("status", "target_test_count", "actual_test_count", "blockers")
                    },
                    indent=2,
                )
            )
        elif args.command == "split-check":
            from .evaluation.review import check_grouped_split

            errors = check_grouped_split(root, json.loads(args.manifest.read_text()))
            print(json.dumps({"errors": errors, "human_review_implied": False}, indent=2))
            if errors:
                sys.exit(1)
        elif args.command == "eval-live":
            from .live import run_live

            config = yaml.safe_load(args.config.read_text())
            result = run_live(
                root, config, args.approval, args.split, args.repetitions, args.resume
            )
            print(json.dumps(result, indent=2))
            if not result["complete"]:
                sys.exit(1)
    except Exception as exc:
        if args.command == "jobs":
            # Driver/configuration exceptions can contain connection information.
            print(
                f"{type(exc).__name__}: workflow operation failed; check local configuration and readiness",
                file=sys.stderr,
            )
        else:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
