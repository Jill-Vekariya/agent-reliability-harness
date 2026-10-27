"""Bounded failure injection against only a caller-named, isolated Stage 1 stack.

No model calls or real external effects. Every run requires a new output path.
Run with the same public image overrides used to start Compose, when applicable.
"""

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8091")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.project.startswith("arh-stage1-") or any(
        c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in args.project
    ):
        parser.error("Use a unique owned project named arh-stage1-*")
    if args.url != "http://127.0.0.1:8091":
        parser.error("Verifier is restricted to the documented loopback endpoint")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write("{}\n")
    record = {
        "schema_version": 1,
        "label": "UNVERIFIED",
        "origin": "synthetic",
        "started_at": datetime.now(UTC).isoformat(),
        "environment": platform.platform(),
        "python": platform.python_version(),
        "project": args.project,
        "invocation": [sys.executable, *sys.argv],
        "commands": [],
        "http": [],
        "scenarios": [],
        "guarantee": "At-least-once attempts with fenced results; synthetic sink deduplication only",
        "source_sha256": hashlib.sha256(
            json.dumps(
                {
                    p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((ROOT / "src").rglob("*.py"))
                },
                sort_keys=True,
            ).encode()
        ).hexdigest(),
    }
    prefix = [
        "docker",
        "compose",
        "--env-file",
        ".env.workflow",
        "-f",
        "compose.workflow.yaml",
        "-p",
        args.project,
    ]
    paused = False
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def save():
        args.output.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")

    def command(argv, timeout=60):
        started = datetime.now(UTC).isoformat()
        try:
            p = subprocess.run(
                argv,
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            record["commands"].append(
                {
                    "at": started,
                    "command": argv,
                    "exit_code": None,
                    "label": "FAILED",
                    "reason": "command timeout",
                    "stdout": (exc.stdout or b"").decode("utf-8", "replace")
                    if isinstance(exc.stdout, bytes)
                    else exc.stdout,
                    "stderr": (exc.stderr or b"").decode("utf-8", "replace")
                    if isinstance(exc.stderr, bytes)
                    else exc.stderr,
                }
            )
            save()
            raise
        record["commands"].append(
            {
                "at": started,
                "command": argv,
                "exit_code": p.returncode,
                "stdout": p.stdout,
                "stderr": p.stderr,
            }
        )
        save()
        if p.returncode:
            raise RuntimeError("Command failed: " + " ".join(argv[:5]))
        return p.stdout

    def compose(*argv):
        return command(prefix + list(argv))

    def request(path, body=None, key=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        req = urllib.request.Request(args.url + path, data=data, headers=headers)
        try:
            response = opener.open(req, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        except OSError as exc:
            record["http"].append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "path": path,
                    "method": "POST" if body is not None else "GET",
                    "request": body,
                    "idempotency_key": key,
                    "status": None,
                    "label": "FAILED",
                    "error_type": type(exc).__name__,
                }
            )
            raise
        with response:
            raw = response.read(2_500_001)
            if len(raw) > 2_500_000:
                raise RuntimeError("Verifier response byte limit")
            value = json.loads(raw)
            status = response.status
        brief = (
            {k: value.get(k) for k in ("id", "state", "attempt_count")}
            if isinstance(value, dict)
            else {"rows": len(value)}
        )
        record["http"].append(
            {
                "at": datetime.now(UTC).isoformat(),
                "method": "POST" if body is not None else "GET",
                "path": path,
                "request": body,
                "idempotency_key": key,
                "status": status,
                "response": brief,
            }
        )
        return status, value

    def wait(probe, seconds=55):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                value = probe()
                if value:
                    return value
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.15)
        raise TimeoutError("Bounded demonstration condition did not occur")

    def ready():
        return request("/ready")[0] == 200

    def submit(**body):
        status, job = request("/jobs", body, uuid.uuid4().hex)
        assert status == 201, (status, job)
        return job

    def get(job):
        status, row = request("/jobs/" + job["id"])
        assert status == 200
        return row

    def terminal(job):
        return wait(lambda: row if (row := get(job))["state"] in {"succeeded", "failed"} else None)

    def attempts(job):
        status, rows = request("/jobs/" + job["id"] + "/attempts")
        assert status == 200
        return rows

    def sink(job, service):
        code = (
            "import sqlite3,json,sys; "
            "db=sqlite3.connect('file:/reports/workflow-effects.sqlite?mode=ro',uri=True); "
            "print(json.dumps({'effects':db.execute('SELECT count(*) FROM effects WHERE id=?',(sys.argv[1],)).fetchone()[0],"
            "'invocations':db.execute('SELECT count(*) FROM invocations WHERE id=?',(sys.argv[1],)).fetchone()[0]}))"
        )
        output = compose("exec", "-T", service, "python", "-c", code, job["id"])
        return json.loads(output)

    def effect_exists(job, service):
        # Initial executor startup may precede sink-file creation. Exit 1 is retained.
        try:
            return sink(job, service)["effects"] == 1
        except RuntimeError:
            return False

    def scenario(name, jobs, detail):
        record["scenarios"].append(
            {
                "name": name,
                "label": "VERIFIED",
                "jobs": [get(j) for j in jobs],
                "attempts": {j["id"]: attempts(j) for j in jobs},
                "observations": detail,
            }
        )
        save()
        print(name + ": VERIFIED", flush=True)

    try:
        record["revision"] = command(["git", "rev-parse", "HEAD"]).strip()
        record["working_tree"] = command(["git", "status", "--porcelain"]).strip()
        record["docker"] = command(
            ["docker", "version", "--format", "{{.Client.Version}}|{{.Server.Version}}"]
        ).strip()
        compose("stop", "worker-a", "worker-b")
        wait(ready)
        one, queued = submit(demo="sleep", delay_seconds=5.0), submit()
        compose("up", "-d", "--no-deps", "worker-a")
        wait(lambda: get(one)["state"] == "running")
        compose("restart", "api")
        wait(ready)
        assert get(one)["payload"] == one["payload"] and get(queued)["payload"] == queued["payload"]
        assert terminal(one)["state"] == terminal(queued)["state"] == "succeeded"
        scenario("api_restart", [one, queued], {"queued_and_active_identity_preserved": True})

        crashed = submit(demo="effect", delay_seconds=5.0)
        wait(lambda: effect_exists(crashed, "worker-a"))
        compose("kill", "-s", "SIGKILL", "worker-a")
        compose("stop", "-t", "2", "worker-a")
        compose("up", "-d", "--no-deps", "worker-b")
        assert terminal(crashed)["state"] == "succeeded"
        rows = attempts(crashed)
        counts = sink(crashed, "worker-b")
        assert [r["state"] for r in rows] == ["lost", "succeeded"]
        assert counts == {"effects": 1, "invocations": 2}
        scenario("worker_kill_and_reexecution", [crashed], counts)

        key = uuid.uuid4().hex
        responses = [request("/jobs", {"task_id": "q001"}, key) for _ in range(3)]
        assert [s for s, _ in responses] == [201, 200, 200]
        assert len({r["id"] for _, r in responses}) == 1
        duplicate = responses[0][1]
        assert request("/jobs", {"task_id": "q002"}, key)[0] == 409
        assert terminal(duplicate)["state"] == "succeeded"
        assert len(attempts(duplicate)) == 1
        scenario(
            "duplicate_admission_and_conflicting_payload",
            [duplicate],
            {
                "same_id_three_submissions": True,
                "conflict_status": 409,
                "actual_duplicate_execution_demonstrated_by_worker_kill": crashed["id"],
            },
        )

        compose("up", "-d", "--no-deps", "worker-a", "worker-b")
        batch = [submit(demo="sleep", delay_seconds=1.0) for _ in range(8)]
        assert all(terminal(j)["state"] == "succeeded" for j in batch)
        rows = [a for j in batch for a in attempts(j)]
        assert len(rows) == len(batch)
        assert {a["worker_id"] for a in rows} == {"worker-a", "worker-b"}
        scenario(
            "competing_workers",
            batch,
            {
                "unique_jobs": 8,
                "attempts": len(rows),
                "workers": sorted({a["worker_id"] for a in rows}),
            },
        )

        compose("stop", "worker-b")
        stale = submit(demo="effect", delay_seconds=5.0)
        wait(lambda: effect_exists(stale, "worker-a"))
        compose("pause", "worker-a")
        paused = True
        compose("up", "-d", "--no-deps", "worker-b")
        assert terminal(stale)["state"] == "succeeded"
        compose("unpause", "worker-a")
        paused = False
        wait(lambda: attempts(stale)[0]["stale_result_rejections"] >= 1, seconds=15)
        rows = attempts(stale)
        counts = sink(stale, "worker-b")
        assert rows[0]["state"] == "lost" and rows[1]["state"] == "succeeded"
        assert counts == {"effects": 1, "invocations": 2}
        scenario(
            "expired_lease_rejects_stale_worker",
            [stale],
            {"stale_result_rejections": rows[0]["stale_result_rejections"], **counts},
        )

        failed = submit(demo="always_fail")
        assert terminal(failed)["state"] == "failed"
        rows = attempts(failed)
        assert len(rows) == 3 and all(r["error_code"] == "synthetic_failure" for r in rows)
        compose("restart", "api")
        wait(ready)
        assert get(failed)["state"] == "failed" and len(attempts(failed)) == 3
        scenario(
            "retry_exhaustion_persists_terminal_failure", [failed], {"failed_attempts_retained": 3}
        )
        assert len(record["scenarios"]) == 6
        record["label"] = "VERIFIED"
        record["exit_code"] = 0
    except Exception as exc:
        record["label"] = "FAILED"
        record["exit_code"] = 1
        record["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
        print("Demonstration FAILED: " + type(exc).__name__, file=sys.stderr)
    finally:
        if paused:
            try:
                compose("unpause", "worker-a")
            except Exception:
                record["cleanup"] = "FAILED: owned worker may remain paused"
        try:
            record["final_container_state"] = compose("ps", "--all", "--format", "json")
            record["worker_logs"] = compose(
                "logs", "--no-color", "--tail", "200", "worker-a", "worker-b"
            )
        except Exception:
            record["log_collection"] = "FAILED"
        record["finished_at"] = datetime.now(UTC).isoformat()
        save()
    raise SystemExit(record["exit_code"])


if __name__ == "__main__":
    main()
