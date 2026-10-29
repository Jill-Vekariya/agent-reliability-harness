"""Restore LF only when normalized bytes exactly match the committed Git blob."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".json", ".jsonl", ".yaml", ".yml"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the evidence path before touching working files.
    stream = args.output.open("x", encoding="utf-8")
    report = {
        "label": "UNVERIFIED",
        "changes": [],
        "left_changed_files": [],
        "mode": "fix" if args.fix else "check",
    }
    try:
        names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
        for name in names:
            path = ROOT / name
            if path.suffix not in SUFFIXES or not path.is_file():
                continue
            raw = path.read_bytes()
            if b"\r\n" not in raw:
                continue
            normalized = raw.replace(b"\r\n", b"\n")
            committed = subprocess.run(
                ["git", "show", "HEAD:" + name], cwd=ROOT, capture_output=True, check=False
            )
            if committed.returncode != 0 or normalized != committed.stdout:
                report["left_changed_files"].append(name)
                continue
            record = {
                "path": name,
                "before_sha256": hashlib.sha256(raw).hexdigest(),
                "committed_sha256": hashlib.sha256(committed.stdout).hexdigest(),
                "normalized_sha256": hashlib.sha256(normalized).hexdigest(),
                "written": args.fix,
            }
            report["changes"].append(record)
            if args.fix:
                path.write_bytes(normalized)
        report["label"] = "VERIFIED" if args.fix or not report["changes"] else "FAILED"
    finally:
        with stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(
        json.dumps(
            {
                "label": report["label"],
                "eligible_files": len(report["changes"]),
                "left_changed_files": report["left_changed_files"],
            }
        )
    )
    raise SystemExit(0 if report["label"] == "VERIFIED" else 1)


if __name__ == "__main__":
    main()
