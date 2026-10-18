"""Execute release checks and preserve actual stdout, stderr, return codes, and counts."""

import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from agent_reliability.runner import environment_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
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
        if result.returncode:
            break
    evidence = {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "environment": environment_manifest(ROOT, {"id": "release-checks"}),
        "commands": records,
        "all_checks_passed": len(records) == len(commands)
        and all(r["exit_code"] == 0 for r in records),
        "fresh_provider_calls": 0,
        "paid_api_spend_usd": "0",
        "human_reviews": 0,
        "public_deployment": False,
        "desktop_checks": "See desktop-verification.json for independent Docker/browser evidence.",
    }
    p = ROOT / "reports/release-evidence.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(evidence, indent=2) + "\n")
    if not evidence["all_checks_passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
