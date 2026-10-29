"""Freeze host Git and source hashes for a measurement container without Git."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "experiments/workflow-stage3.v2.protocol.json"
    )
    args = parser.parse_args()

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    files = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted((ROOT / "src").rglob("*.py"))}
    context = {
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True),
        "source_sha256": hashlib.sha256(
            json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "dependency_lock_sha256": sha(ROOT / "uv.lock"),
        "script_sha256": sha(ROOT / "scripts/measure_workflow.py"),
        "protocol_sha256": sha(args.protocol),
        "attestation": "Operator-supplied host metadata, not an independent signature; runtime hashes are rechecked by the measurement driver",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(context, stream, indent=2)
        stream.write("\n")
    print("Created source context; no environment values or credentials were read")


if __name__ == "__main__":
    main()
