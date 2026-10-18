"""Execute release checks and preserve actual stdout, stderr, return codes, and counts."""

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from agent_reliability.runner import environment_manifest
from agent_reliability.util import write_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Capture the full offline audit, including expected-denial checks",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports/release-evidence.json")
    args = parser.parse_args()
    commands = [
        ["make", "data"],
        ["make", "lint"],
        ["make", "typecheck"],
        ["make", "test"],
        [sys.executable, "-m", "agent_reliability.cli", "validate-tasks"],
        ["make", "eval"],
        ["make", "eval", "MODE=replay"],
        ["make", "estimate"],
        ["make", "report"],
    ]
    expected_codes: dict[tuple[str, ...], int] = {}
    if args.audit:
        commands = [
            ["uv", "lock", "--check", "--offline"],
            ["make", "ci"],
            [sys.executable, "-m", "agent_reliability.cli", "eval", "--all"],
            [sys.executable, "-m", "agent_reliability.cli", "eval", "--mode", "fixture", "--all"],
            ["make", "eval", "MODE=replay"],
            [
                sys.executable,
                "-m",
                "agent_reliability.cli",
                "review-check",
                "--packet",
                "reviews/benchmark-candidates.json",
                "--require-complete",
            ],
            ["make", "estimate"],
            ["make", "report"],
            ["make", "public-demo"],
        ]
        expected_codes[tuple(commands[5])] = 1  # All real reviews remain pending.
    records = []
    for command in commands:
        start = datetime.now(UTC).isoformat()
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        output = result.stdout + result.stderr
        counts = {
            name: int(match.group(1)) if (match := re.search(r"(\d+) " + name, output)) else 0
            for name in ["passed", "failed", "skipped"]
        }
        record = {
            "command": command,
            "started_at": start,
            "finished_at": datetime.now(UTC).isoformat(),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "expected_exit_code": expected_codes.get(tuple(command), 0),
        }
        if any(counts.values()):
            record["test_counts"] = counts
        records.append(record)
        print(
            json.dumps(
                {"command": " ".join(command), "exit_code": result.returncode, "counts": counts}
            ),
            flush=True,
        )
        if result.returncode != record["expected_exit_code"]:
            break
    evidence = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "environment": environment_manifest(ROOT, {"id": "release-checks"}),
        "commands": records,
        "all_checks_passed": len(records) == len(commands)
        and all(r["exit_code"] == r["expected_exit_code"] for r in records),
        "fresh_provider_calls": 0,
        "paid_api_spend_usd": "0",
        "human_reviews": 0,
        "public_deployment": False,
        "desktop_checks": "See desktop-verification.json for independent Docker/browser evidence.",
    }
    evidence["scope"] = "unpublished local audit" if args.audit else "local release checks"
    if args.audit:
        evidence["desktop_checks"] = (
            "See audit-desktop.json; audit image is a local build, not a published release."
        )
        evidence["historical_external_evidence"] = (
            "See audit-external.json; v0.2.1 hosted results do not validate this audit branch."
        )
    write_json(args.output, evidence)
    if not evidence["all_checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
