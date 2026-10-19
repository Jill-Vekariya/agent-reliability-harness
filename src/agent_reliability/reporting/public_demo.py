"""Export only explicitly selected, hash-validated synthetic traces for GitHub Pages.

This creates a static walkthrough, never a SQL executor or model endpoint. Full
provider requests and evaluator-only gold are deliberately absent from the export.
"""

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from agent_reliability.evaluation.tasks import load_tasks
from agent_reliability.tracing.recording import load_trace
from agent_reliability.util import file_hash

CASES = (
    ("q001", "Supported answer", "demo/traces/q001.json"),
    ("q002", "Schema failure", "demo/traces/q002.json"),
    ("s001", "Blocked injection", "demo/traces/s001.json"),
    ("recovery", "Scripted recovery", "demo/recovery.json"),
)


def published_verification(root: Path) -> dict[str, Any]:
    """Publish a count only from the explicitly selected, checksum-bound release."""
    reports = root / "reports"
    index_path = reports / "public-evidence.json"
    if not index_path.exists():
        evidence = json.loads((reports / "release-evidence.json").read_text(encoding="utf-8"))
        return {
            "captured_at": evidence["captured_at"],
            "all_checks_passed": evidence["all_checks_passed"],
            "test_counts": next(
                (
                    r.get("test_counts")
                    for r in evidence["commands"]
                    if r["command"] == ["make", "test"]
                ),
                None,
            ),
        }
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if (
        not isinstance(index, dict)
        or set(index) != {"schema_version", "source", "sha256"}
        or type(index.get("schema_version")) is not int
        or index["schema_version"] != 1
        or not isinstance(index.get("source"), str)
    ):
        raise ValueError("Invalid public evidence index")
    source = reports / index["source"]
    if Path(index["source"]).is_absolute() or not source.resolve().is_relative_to(
        reports.resolve()
    ):
        raise ValueError("Public evidence path escapes reports")
    if file_hash(source) != index["sha256"]:
        raise ValueError("Public evidence checksum mismatch")
    record = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("Public evidence must be an object")
    counts, workflows = record.get("published_image_tests", {}), record.get("hosted_workflows", [])
    valid = (
        isinstance(counts, dict)
        and all(
            type(counts.get(k)) is int and counts[k] >= 0 for k in ("passed", "failed", "skipped")
        )
        and counts["passed"] > 0
        and counts["failed"] == 0
        and record.get("installed_source_matches_checkout") is True
        and isinstance(workflows, list)
        and bool(workflows)
        and all(
            isinstance(w, dict)
            and w.get("status") == "completed"
            and w.get("conclusion") == "success"
            for w in workflows
        )
        and isinstance(record.get("release"), str)
    )
    return {
        "captured_at": record.get("captured_at", "unavailable"),
        "release": record.get("release"),
        "source": index["source"],
        "source_sha256": index["sha256"],
        "all_checks_passed": bool(valid),
        "test_counts": {k: counts[k] for k in ("passed", "failed", "skipped")} if valid else None,
    }


def public_payload(root: Path) -> dict[str, Any]:
    tasks = {task.id: task for task in load_tasks(root)}
    cases = []
    for case_id, title, relative in CASES:
        path = root / relative
        trace = load_trace(path)
        if trace.origin != "synthetic":
            raise ValueError("Public demo accepts explicitly synthetic traces only")
        task = tasks[trace.task_id]
        cases.append(
            {
                "id": case_id,
                "title": title,
                "question": task.question,
                "category": task.category,
                "origin": trace.origin,
                "termination": trace.termination,
                "config": trace.config,
                "final": trace.final,
                "steps": [
                    {
                        "index": event.index,
                        "name": event.payload["name"],
                        "arguments": event.payload["arguments"],
                        "output": event.payload["output"],
                    }
                    for event in trace.events
                    if event.kind == "tool"
                ],
                "source": relative,
                "source_sha256": file_hash(path),
            }
        )
    return {
        "schema_version": 1,
        "mode": "static synthetic walkthrough; no SQL or model execution",
        "candidate_tasks": len(tasks),
        "reviewed_tasks": sum(task.review_status == "human_reviewed" for task in tasks.values()),
        "verification": published_verification(root),
        "cases": cases,
    }


def safe_json(payload: Any) -> str:
    # A JSON data block is still inside HTML: prevent </script> and HTML parsing.
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def csp_hash(content: str) -> str:
    return base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()


def build(root: Path, output: Path) -> Path:
    payload = public_payload(root)
    # The HTML declares UTF-8 and CSP hashes are computed over UTF-8 bytes.
    # A host's default encoding must not change either the text or those hashes.
    template = (root / "web/index.html").read_text(encoding="utf-8")
    style = (root / "web/style.css").read_text(encoding="utf-8")
    script = (root / "web/app.js").read_text(encoding="utf-8")
    html = (
        template.replace("__STYLE_HASH__", csp_hash(style))
        .replace("__SCRIPT_HASH__", csp_hash(script))
        .replace("__STYLE__", style)
        .replace("__SCRIPT__", script)
        .replace("__DEMO_DATA__", safe_json(payload))
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / "index.html"
    path.write_text(html, encoding="utf-8", newline="\n")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    return path
