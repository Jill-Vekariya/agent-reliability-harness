"""Record bounded Stage 2 checks; no live calls, secret dumps or overwritten receipts."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records: list[dict] = []
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    sources = sorted(
        p
        for folder in ["src", "tests", "scripts", "docs"]
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    sources += [
        ROOT / p
        for p in ["pyproject.toml", "uv.lock", "compose.workflow.yaml", "Dockerfile.workflow"]
    ]
    fingerprint = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
    }
    report = {
        "revision": revision,
        "dirty": dirty,
        "source_sha256": hashlib.sha256(
            json.dumps(fingerprint, sort_keys=True).encode()
        ).hexdigest(),
        "environment": platform.platform(),
        "python": sys.version,
        "started_at": datetime.now(UTC).isoformat(),
        "commands": records,
    }

    def save() -> None:
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (output / "source-hashes.json").write_text(
            json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8"
        )

    def run(command: list[str], label: str) -> None:
        log = output / f"{len(records):02d}-{label}.log"
        record = {"command": command, "label": "RUNNING", "log": log.name}
        records.append(record)
        save()
        try:
            with log.open("w", encoding="utf-8") as stream:
                result = subprocess.run(
                    command,
                    cwd=ROOT,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                    env={**os.environ, "ARH_PROJECT_ROOT": str(ROOT)},
                )
            record.update(
                exit_code=result.returncode,
                label="VERIFIED" if result.returncode == 0 else "FAILED",
            )
        except subprocess.TimeoutExpired:
            record.update(
                exit_code=None, label="FAILED", reason="300-second stopping limit exceeded"
            )
        save()
        print(label + ": " + record["label"], flush=True)

    prefix = [sys.executable]
    # Run inside the locked environment: uv run --no-sync python scripts/verify_workflow_controls.py ...
    run(prefix + ["-m", "agent_reliability.cli", "data"], "fixture-data")
    run(prefix + ["-m", "ruff", "check", "src", "tests", "scripts"], "lint")
    run(prefix + ["-m", "ruff", "format", "--check", "src", "tests", "scripts"], "format")
    run(prefix + ["-m", "mypy", "src"], "types")
    run(prefix + ["-m", "pytest", "-q", "--junitxml=" + str(output / "all-tests.xml")], "all-tests")
    for command in [
        ["validate-tasks"],
        ["review-check", "--packet", "reviews/benchmark-candidates.json"],
        ["split-check", "--manifest", "tasks/grouped-split.proposal.json"],
        ["eval"],
    ]:
        run(prefix + ["-m", "agent_reliability.cli"] + command, command[0])
    if os.environ.get("ARH_WORKFLOW_TEST_DATABASE_URL"):
        run(
            prefix
            + [
                "-m",
                "pytest",
                "tests/integration/test_workflow_postgres.py",
                "-q",
                "--junitxml=" + str(output / "postgres-tests.xml"),
            ],
            "real-postgres",
        )
    else:
        records.append(
            {
                "label": "BLOCKED",
                "check": "real PostgreSQL",
                "reason": "ARH_WORKFLOW_TEST_DATABASE_URL is not configured; database tests skipped, not verified",
                "exit_code": None,
            }
        )
    failed = any(r["label"] == "FAILED" for r in records)
    blocked = any(r["label"] == "BLOCKED" for r in records)
    report["label"] = "FAILED" if failed else "PARTIALLY VERIFIED" if blocked else "VERIFIED"
    report["finished_at"] = datetime.now(UTC).isoformat()
    save()
    print(report["label"] + ": " + str(output))
    raise SystemExit(1 if failed else 2 if blocked else 0)


if __name__ == "__main__":
    main()
