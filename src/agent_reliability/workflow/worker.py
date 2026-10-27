"""Renewable job leases supervise a separate bounded fixture process."""

import json
import logging
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import psycopg

from ..util import canonical
from .models import MAX_RESULT_BYTES
from .store import Claim, Store

log = logging.getLogger(__name__)


def failure(code: str, *, retryable: bool = True) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "retryable": retryable}


def child_environment(root: Path, effects: Path, parent: int) -> dict[str, str]:
    """Exclude DSN, API credentials, user PYTHONPATH and inherited proxies."""
    return {
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ARH_PROJECT_ROOT": str(root.resolve()),
        "ARH_WORKFLOW_EFFECTS": str(effects.resolve()),
        "ARH_WORKFLOW_PARENT_PID": str(parent),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }


def cleanup(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=0.3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait(timeout=2)
    if proc.stdout:
        proc.stdout.close()
    if proc.stdin:
        proc.stdin.close()


def supervise(
    store: Store, claim: Claim, root: Path, effects: Path, stop: threading.Event
) -> dict[str, Any]:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise RuntimeError("Durable workers require Linux; use Docker on Windows/macOS")
    proc = subprocess.Popen(
        [sys.executable, "-I", "-m", "agent_reliability.workflow.executor"],
        cwd=root,
        env=child_environment(root, effects, os.getpid()),
        start_new_session=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    log.info(
        canonical(
            {
                "event": "attempt_process",
                "job_id": claim.job_id,
                "attempt": claim.number,
                "worker_id": claim.worker_id,
                "pid": proc.pid,
            }
        )
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None
        payload = canonical(
            {"job_id": claim.job_id, "attempt": claim.number, "payload": claim.payload}
        ).encode()
        if len(payload) > 16384:
            return failure("input_limit", retryable=False)
        sent = 0
        output = bytearray()
        os.set_blocking(proc.stdin.fileno(), False)
        os.set_blocking(proc.stdout.fileno(), False)
        started = time.monotonic()
        deadline = started + claim.timeout_seconds
        heartbeat = started + store.policy.heartbeat_seconds
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdin, selectors.EVENT_WRITE, "input")
            selector.register(proc.stdout, selectors.EVENT_READ, "output")
            while True:
                now = time.monotonic()
                if stop.is_set():
                    return failure("worker_stopping")
                if now >= deadline:
                    return failure("attempt_timeout")
                if now >= heartbeat:
                    try:
                        valid = store.heartbeat(claim)
                    except psycopg.Error:
                        return failure("heartbeat_unavailable")
                    if not valid:
                        return failure("lease_lost")
                    heartbeat = time.monotonic() + store.policy.heartbeat_seconds
                for key, _ in selector.select(max(0, min(0.1, deadline - now, heartbeat - now))):
                    if key.data == "input":
                        try:
                            sent += os.write(proc.stdin.fileno(), payload[sent : sent + 4096])
                        except BrokenPipeError:
                            sent = len(payload)
                        if sent == len(payload):
                            selector.unregister(proc.stdin)
                            proc.stdin.close()
                    else:
                        part = os.read(proc.stdout.fileno(), 8192)
                        if part:
                            if len(output) + len(part) > MAX_RESULT_BYTES:
                                return failure("output_limit", retryable=False)
                            output.extend(part)
                        else:
                            proc.wait(timeout=max(0.01, deadline - time.monotonic()))
                            if proc.returncode != 0:
                                return failure("executor_exit")
                            try:
                                result = json.loads(output)
                            except (ValueError, UnicodeDecodeError):
                                return failure("invalid_executor_result", retryable=False)
                            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                                return failure("invalid_executor_result", retryable=False)
                            return result
    except (OSError, subprocess.TimeoutExpired):
        return failure("executor_transport")
    finally:
        cleanup(proc)


def run_worker(
    store: Store, root: Path, worker_id: str, effects: Path, stop: threading.Event | None = None
) -> None:
    stopping = stop or threading.Event()
    while not stopping.is_set():
        try:
            claim = store.claim(worker_id)
            if claim is None:
                stopping.wait(store.policy.poll_seconds)
                continue
            log.info(
                canonical(
                    {
                        "event": "claimed",
                        "job_id": claim.job_id,
                        "attempt": claim.number,
                        "worker_id": worker_id,
                    }
                )
            )
            result = supervise(store, claim, root, effects, stopping)
            accepted = store.finish(claim, result)
            log.info(
                canonical(
                    {
                        "event": "result_committed" if accepted else "stale_result_rejected",
                        "job_id": claim.job_id,
                        "attempt": claim.number,
                        "worker_id": worker_id,
                        "ok": result["ok"],
                        "error_code": result.get("error_code"),
                    }
                )
            )
        except psycopg.Error:
            log.warning(canonical({"event": "database_unavailable", "worker_id": worker_id}))
            stopping.wait(max(1.0, store.policy.poll_seconds))
