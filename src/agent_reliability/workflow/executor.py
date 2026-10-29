"""One credential-free fixture attempt; never constructs a live provider."""

import ctypes
import json
import os
import signal
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from ..agents.sql import SQLAgent
from ..evaluation.grading import grade
from ..evaluation.tasks import database_for_task, load_tasks
from ..models import Limits
from ..providers.fixture import FixtureProvider
from ..sandbox import Sandbox
from ..util import canonical, digest
from .catalog import resolved_payload
from .models import MAX_RESULT_BYTES, JobRequest


def synthetic_effect(path: Path, job_id: str, payload_hash: str, attempt: int) -> dict[str, Any]:
    """Separate synthetic sink: deduplicate one effect, retain every invocation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=2) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS effects (id TEXT PRIMARY KEY,payload_hash TEXT NOT NULL)"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS invocations (id TEXT,attempt INTEGER)")
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO invocations VALUES(?,?)", (job_id, attempt))
        row = conn.execute("SELECT payload_hash FROM effects WHERE id=?", (job_id,)).fetchone()
        if row and row[0] != payload_hash:
            raise ValueError("Synthetic effect payload conflict")
        conn.execute("INSERT OR IGNORE INTO effects VALUES(?,?)", (job_id, payload_hash))
        return {"logical_effect_id": job_id, "deduplicated": row is not None}


def execute(root: Path, message: dict[str, Any]) -> dict[str, Any]:
    payload = message["payload"]
    request = JobRequest.model_validate(payload["request"])
    if resolved_payload(root, request) != payload:
        return {"ok": False, "error_code": "provenance_changed", "retryable": False}
    if request.demo == "provider":
        # Deterministic bounded local provider; no network, key or billable SDK.
        time.sleep(request.delay_seconds)
        return {
            "ok": True,
            "fake_provider": {"usage_units": 6 if request.fake_usage == "known" else None},
        }
    attempt = message["attempt"]
    if request.demo == "always_fail" or (request.demo == "fail_once" and attempt == 1):
        return {"ok": False, "error_code": "synthetic_failure", "retryable": True}
    effect = None
    if request.demo == "effect":
        effect = synthetic_effect(
            Path(os.environ["ARH_WORKFLOW_EFFECTS"]), message["job_id"], digest(payload), attempt
        )
    if request.demo in {"sleep", "effect"}:
        time.sleep(request.delay_seconds)
    task = next(t for t in load_tasks(root) if t.id == request.task_id)
    script = json.loads(
        (root / "tests/fixtures/provider_scripts.json").read_text(encoding="utf-8")
    )["scripts"][task.id]
    trace = SQLAgent(
        FixtureProvider(script),
        Sandbox(database_for_task(root, task), Limits()),
        {"id": "durable-fixture-v1", "model": "synthetic-fixture-v1", "retry_on_error": 0},
        attempt_id=f"{message['job_id']}:{attempt}",
    ).run(task.agent_input())
    if trace.infrastructure_error:
        return {
            "ok": False,
            "error_code": "fixture_infrastructure",
            "retryable": False,
            "trace": trace.model_dump(mode="json"),
        }
    return {
        "ok": True,
        "trace": trace.model_dump(mode="json"),
        "grade": grade(task, trace).model_dump(mode="json"),
        "synthetic_effect": effect,
    }


def own_process_group() -> None:
    """Linux parent-death cleanup without a threaded-process preexec_fn."""
    parent = int(os.environ["ARH_WORKFLOW_PARENT_PID"])
    if os.getpgrp() != os.getpid():
        raise RuntimeError("Attempt must have its own process group")

    def terminate_group(signum: int, frame: Any) -> None:
        os.killpg(os.getpgrp(), signal.SIGKILL)

    signal.signal(signal.SIGTERM, terminate_group)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise RuntimeError("Linux parent-death signal unavailable")
    if os.getppid() != parent:
        terminate_group(signal.SIGTERM, None)


def main() -> None:
    try:
        own_process_group()
        message = json.loads(sys.stdin.buffer.read(16384))
        result = execute(Path(os.environ["ARH_PROJECT_ROOT"]), message)
        encoded = canonical(result).encode()
        if len(encoded) > MAX_RESULT_BYTES:
            raise ValueError("Attempt result limit")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
    except Exception as exc:
        print(
            canonical(
                {
                    "ok": False,
                    "error_code": "executor_error",
                    "retryable": False,
                    "diagnostic_type": type(exc).__name__,
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
