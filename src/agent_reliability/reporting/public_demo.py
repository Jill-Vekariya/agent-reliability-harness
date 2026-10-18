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
    evidence = json.loads((root / "reports/release-evidence.json").read_text())
    return {
        "schema_version": 1,
        "mode": "static synthetic walkthrough; no SQL or model execution",
        "candidate_tasks": len(tasks),
        "reviewed_tasks": sum(task.review_status == "human_reviewed" for task in tasks.values()),
        "verification": {
            "captured_at": evidence["captured_at"],
            "all_checks_passed": evidence["all_checks_passed"],
            "test_counts": next(
                (
                    record.get("test_counts")
                    for record in evidence["commands"]
                    if record["command"] == ["make", "test"]
                ),
                None,
            ),
        },
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
    template = (root / "web/index.html").read_text()
    style = (root / "web/style.css").read_text()
    script = (root / "web/app.js").read_text()
    html = (
        template.replace("__STYLE_HASH__", csp_hash(style))
        .replace("__SCRIPT_HASH__", csp_hash(script))
        .replace("__STYLE__", style)
        .replace("__SCRIPT__", script)
        .replace("__DEMO_DATA__", safe_json(payload))
    )
    output.mkdir(parents=True, exist_ok=True)
    path = output / "index.html"
    path.write_text(html)
    (output / ".nojekyll").write_text("")
    return path
