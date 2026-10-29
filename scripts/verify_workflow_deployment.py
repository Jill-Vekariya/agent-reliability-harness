"""Reproduce the bounded, private Stage 5 local deployment and recovery check.

Uses only task-selected Compose projects. Teardown retains persistent volumes.
All provider operations are deterministic fakes; no external AI calls occur.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from scripts.workflow_ops import Ops, credentials  # noqa: E402


class Verification:
    def __init__(self, project: str, port: int, output: Path) -> None:
        if not 1024 <= port <= 65534:
            raise ValueError("Bounded loopback port required")
        output.mkdir(parents=True, exist_ok=False)
        self.output, self.project, self.port = output, project, port
        self.metadata = ROOT / ".local/stage5-deployment.json"
        self.counter = 0
        self.receipts: list[dict[str, Any]] = []
        self.owned_projects: set[str] = set()
        self.env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "ARH_WORKFLOW_API_PORT": str(port),
            "ARH_WORKFLOW_IMAGE": "arh-workflow:stage5-local",
            "ARH_WORKFLOW_CHECKS_IMAGE": "arh-workflow:stage5-checks-local",
        }
        self.ops: Ops

    def record(
        self, name: str, command: list[str], *, timeout: int = 180, expected: int = 0
    ) -> bytes:
        self.counter += 1
        stem = f"{self.counter:02d}-{name}"
        start = time.monotonic()
        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                env=self.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
            code, data = proc.returncode, proc.stdout
        except subprocess.TimeoutExpired as exc:
            code, data = 124, exc.stdout or b""
        (self.output / (stem + ".log")).write_bytes(data)
        item = {
            "name": name,
            "command": command,
            "exit_code": code,
            "expected_exit": expected,
            "elapsed_seconds": time.monotonic() - start,
            "cwd": str(ROOT),
            "label": "VERIFIED" if code == expected else "FAILED",
        }
        self.receipts.append(item)
        (self.output / "commands.json").write_text(json.dumps(self.receipts, indent=2))
        print(json.dumps(item), flush=True)
        if code != expected:
            raise RuntimeError("Verification command failed: " + name)
        return data

    def compose(self, name: str, *args: str, **kwargs: Any) -> bytes:
        return self.record(name, [*self.ops.prefix, *args], **kwargs)

    def initialize(self) -> None:
        if not (ROOT / ".env.workflow").exists():
            self.record("configure", [sys.executable, "scripts/configure_workflow.py"])
        self.ops = Ops(self.project)
        self.env.update(credentials(ROOT))
        self.ops.env.update(self.env)
        self.record(
            "config-validation",
            [sys.executable, "scripts/workflow_ops.py", "--project", self.project, "validate"],
        )

    def build(self) -> None:
        self.ops.fresh()
        self.owned_projects.add(self.project)
        runtime = [p for base in (ROOT / "src", ROOT / "scripts") for p in base.rglob("*.py")]
        runtime += list((ROOT / "tests").rglob("*.py"))
        # These byte-bound fixtures and evidence files are copied into both
        # images. A checkout-only line-ending repair must invalidate old images.
        runtime += [
            p
            for name in ("data", "tasks", "reports", "reviews", "experiments", "tests/regression")
            for p in (ROOT / name).rglob("*")
            if p.is_file()
        ]
        runtime += list((ROOT / "src/agent_reliability/workflow/sql").glob("*.sql"))
        runtime += [
            ROOT / n
            for n in (
                "pyproject.toml",
                "uv.lock",
                "Dockerfile.workflow",
                "compose.workflow.yaml",
                ".python-version",
                ".dockerignore",
                ".gitattributes",
                "scripts/workflow_init.sql",
            )
        ]
        hashes = {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(runtime)
        }
        source = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        self.env.update(ARH_WORKFLOW_SOURCE_REVISION=revision, ARH_WORKFLOW_SOURCE_DIGEST=source)
        self.compose("default-build", "--profile", "checks", "build", "api", "checks", timeout=1800)
        image = self.ops.image()
        labels = self.ops.inspect(image)["Config"].get("Labels", {})
        if labels.get("io.arh.workflow.source_digest") != source:
            raise ValueError("Built image does not match the selected source digest")
        checks = self.ops.inspect(self.env["ARH_WORKFLOW_CHECKS_IMAGE"])
        if checks["Config"].get("Labels", {}).get("io.arh.workflow.source_digest") != source:
            raise ValueError("Checks image does not match the selected source digest")
        self.metadata.parent.mkdir(parents=True, exist_ok=True)
        self.metadata.write_text(
            json.dumps(
                {
                    "project": self.project,
                    "image_id": image,
                    "checks_image_id": checks["Id"],
                    "base_revision": revision,
                    "source_digest": source,
                    "source_hashes": hashes,
                },
                indent=2,
            )
        )
        (self.output / "build-context.json").write_text(self.metadata.read_text())

    def selected_image(self) -> str:
        metadata = json.loads(self.metadata.read_text())
        if metadata["project"] != self.project:
            raise ValueError("Deployment metadata belongs to a different project")
        for name, expected in metadata["source_hashes"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError("Source changed since verified build; rebuild before continuing")
        image = metadata["image_id"]
        checks_image = metadata.get("checks_image_id")
        if not checks_image:
            raise ValueError("Checks image receipt is missing; rebuild before continuing")
        for selected in (image, checks_image):
            labels = self.ops.inspect(selected)["Config"].get("Labels", {})
            if labels.get("io.arh.workflow.source_digest") != metadata["source_digest"]:
                raise ValueError("Selected image does not match the recorded source digest")
        self.env["ARH_WORKFLOW_IMAGE"] = image
        self.env["ARH_WORKFLOW_CHECKS_IMAGE"] = checks_image
        self.ops.env.update(self.env)
        self.owned_projects.add(self.project)
        return image

    def tests(self) -> None:
        self.selected_image()
        self.compose("database-start", "up", "-d", "workflow-db")
        self.ops.wait_database()
        for name in ("migration-first", "migration-reentry"):
            self.compose(name, "run", "--rm", "-T", "migrate")
        try:
            self.compose(
                "full-tests",
                "--profile",
                "checks",
                "run",
                "--rm",
                "-T",
                "checks",
                "python",
                "-m",
                "pytest",
                "-q",
                "-o",
                "cache_dir=/tmp/pytest-cache",
                "--junitxml=/reports/stage5-tests.xml",
                timeout=420,
            )
        finally:
            xml = self.ops.compose(
                "--profile",
                "checks",
                "run",
                "--rm",
                "--no-deps",
                "-T",
                "--entrypoint",
                "cat",
                "checks",
                "/reports/stage5-tests.xml",
            )
            (self.output / "full-tests.xml").write_bytes(xml)

    def request(
        self,
        path: str,
        token: str | None = None,
        *,
        body: Any = None,
        key: str | None = None,
        port: int | None = None,
    ) -> tuple[int, Any, Any]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if key:
            headers["Idempotency-Key"] = key
        request = urllib.request.Request(
            f"http://127.0.0.1:{port or self.port}" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            # Readiness includes a database connection/query. The stopped-DB
            # probe took 4.234s on Docker Desktop; keep a bounded 10s response
            # deadline while ordinary API calls retain their 4s deadline.
            response = opener.open(request, timeout=10 if path == "/ready" else 4)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            content = response.read(2_000_001)
            if len(content) > 2_000_000:
                raise ValueError("Demo response limit exceeded")
            return (
                response.status,
                (content.decode() if path == "/metrics" else json.loads(content)),
                response.headers,
            )

    def ready(self, port: int | None = None) -> None:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                if self.request("/ready", port=port)[0] == 200:
                    return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(0.5)
        raise RuntimeError("Bounded API readiness deadline exceeded")

    def fingerprint(self, ops: Ops) -> dict[str, Any]:
        results = {}
        for table in (
            "workflow_jobs",
            "workflow_attempts",
            "workflow_approvals",
            "workflow_operations",
            "workflow_budgets",
            "workflow_schema_migrations",
        ):
            query = (
                "SELECT json_build_object('count',count(*),'sha256',encode(sha256(convert_to("
                "coalesce(string_agg(value,'|' ORDER BY value),''),'UTF8')),'hex')) "
                f"FROM (SELECT row_to_json(t)::text AS value FROM {table} t) x"
            )
            results[table] = json.loads(
                ops.compose(
                    "exec",
                    "-T",
                    "workflow-db",
                    "psql",
                    "-U",
                    "arh",
                    "-d",
                    "arh_workflow",
                    "-A",
                    "-t",
                    "-c",
                    query,
                )
            )
        return results

    def effects(self, ops: Ops) -> dict[str, Any]:
        code = (
            "import sqlite3,json,hashlib; c=sqlite3.connect('file:/reports/workflow-effects.sqlite?mode=ro',uri=True);"
            "r={t:c.execute('SELECT * FROM '+t+' ORDER BY 1,2').fetchall() for t in ['effects','invocations']};"
            "print(json.dumps({'counts':{t:len(v) for t,v in r.items()},'sha256':hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()}))"
        )
        return json.loads(
            ops.compose(
                "run", "--rm", "--no-deps", "-T", "--entrypoint", "python", "worker-a", "-c", code
            )
        )

    def demo(self) -> None:
        image = self.selected_image()
        self.compose("application-start", "up", "-d", "api", "worker-a", "worker-b")
        self.ready()
        identities = json.loads((ROOT / ".local/workflow-auth.json").read_text())
        submitter = next(
            k
            for k, v in identities.items()
            if v["tenant_id"] == "tenant-a" and not v["can_approve"]
        )
        approver = next(
            k for k, v in identities.items() if v["tenant_id"] == "tenant-a" and v["can_approve"]
        )
        other = next(k for k, v in identities.items() if v["tenant_id"] == "tenant-b")
        assert self.request("/jobs")[0] == 401 and self.request("/metrics")[0] == 401
        self.compose(
            "synthetic-budget",
            "run",
            "--rm",
            "-T",
            "--no-deps",
            "migrate",
            "arh",
            "jobs",
            "set-budget",
            "--tenant",
            "tenant-a",
            "--limit-units",
            "100",
        )
        jobs = []
        correlation = None
        for demo, usage in [
            ("none", "known"),
            ("effect", "known"),
            ("provider", "known"),
            ("provider", "missing_usage"),
        ]:
            body = {"task_id": "q001", "demo": demo, "fake_usage": usage}
            key = "stage5-" + uuid.uuid4().hex
            status, row, headers = self.request("/jobs", submitter, body=body, key=key)
            assert status == 201
            job = row["id"]
            if correlation is None:
                correlation = {
                    "job_id": job,
                    "request_id": headers["X-Request-ID"],
                    "trace_id": headers["X-Trace-ID"],
                }
            assert self.request("/jobs", submitter, body=body, key=key)[1]["id"] == job
            if row["approval_required"]:
                approvals = self.request("/approvals", approver)[1]
                approval = next(a for a in approvals if a["job_id"] == job)
                status, _, _ = self.request(
                    f"/approvals/{approval['id']}/decision",
                    approver,
                    body={
                        "decision": "approved",
                        "action_hash": row["payload_hash"],
                        "action_version": row["action_version"],
                    },
                )
                assert status == 200
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                row = self.request("/jobs/" + job, submitter)[1]
                if row["state"] in ("succeeded", "failed", "cancelled"):
                    break
                time.sleep(0.3)
            assert row["state"] == "succeeded"
            assert self.request("/jobs/" + job, other)[0] == 404
            jobs.append(
                {
                    "id": job,
                    "state": row["state"],
                    "demo": demo,
                    "usage": usage,
                    "key": key,
                    "request": body,
                }
            )
        budget = self.request("/budget", submitter)[1]
        assert budget["spent_units"] == 6 and budget["reserved_units"] == 10
        assert not self.request("/jobs", other)[1]
        metrics = self.request("/metrics", submitter)[1]
        assert 'arh_workflow_jobs{state="succeeded"} 4' in metrics
        assert 'arh_workflow_jobs{state="succeeded"} 0' in self.request("/metrics", other)[1]
        (self.output / "tenant-metrics.prom").write_text(metrics)
        logs = self.compose(
            "application-logs",
            "logs",
            "--no-color",
            "--no-log-prefix",
            "api",
            "worker-a",
            "worker-b",
        )
        events = []
        for line in logs.decode(errors="replace").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        spans = [e for e in events if e.get("event") == "workflow_span"]
        assert correlation
        http = next(
            e
            for e in spans
            if e["name"] == "workflow.http" and e["trace_id"] == correlation["trace_id"]
        )
        attempt = next(
            e
            for e in spans
            if e["name"] == "workflow.attempt"
            and e["attributes"].get("job_id") == correlation["job_id"]
        )
        assert (
            attempt["trace_id"] == http["trace_id"] and attempt["parent_span_id"] == http["span_id"]
        )
        # Exercise health semantics only on this newly created task database.
        self.compose("task-database-stop", "stop", "workflow-db")
        health = {}
        for endpoint, expected in (("/live", 200), ("/ready", 503)):
            started = time.monotonic()
            status = self.request(endpoint)[0]
            health[endpoint] = {"status": status, "elapsed_seconds": time.monotonic() - started}
            (self.output / "health-observations.json").write_text(json.dumps(health, indent=2))
            assert status == expected
        self.compose("task-database-restart", "start", "workflow-db")
        self.ops.wait_database()
        self.ready()
        original = self.fingerprint(self.ops)
        effect = self.effects(self.ops)
        backup = self.output / "backup"
        self.record(
            "coordinated-backup",
            [
                sys.executable,
                "scripts/workflow_ops.py",
                "--project",
                self.project,
                "--image",
                image,
                "backup",
                str(backup),
            ],
        )
        restored_project = self.project + "-r-" + uuid.uuid4().hex[:6]
        # Do not include an existing/foreign target in failure teardown.
        Ops(restored_project).fresh()
        self.owned_projects.add(restored_project)
        self.restored_project = restored_project
        self.record(
            "fresh-restore",
            [
                sys.executable,
                "scripts/workflow_ops.py",
                "--project",
                restored_project,
                "restore",
                str(backup),
            ],
        )
        restored = Ops(restored_project, image=image)
        restored.env.update(self.env)
        restored.env["ARH_WORKFLOW_API_PORT"] = str(self.port + 1)
        assert self.fingerprint(restored) == original and self.effects(restored) == effect
        refusal = self.record(
            "existing-target-refused",
            [
                sys.executable,
                "scripts/workflow_ops.py",
                "--project",
                restored_project,
                "restore",
                str(backup),
            ],
            expected=1,
        )
        assert b"Restore refuses existing project containers or persistent volumes" in refusal
        # Stage 3's already available image cannot safely run the Stage 5 schema.
        old = "sha256:dca37f82d59e2ad0b0c98732895895c2f0263c31837d2d33955ca3d4d137e4e6"
        refusal = self.record(
            "incompatible-rollback-refused",
            [
                sys.executable,
                "scripts/workflow_ops.py",
                "--project",
                self.project,
                "--image",
                old,
                "rollback",
            ],
            expected=1,
        )
        assert b"Image/schema incompatible" in refusal
        # Known-image restart verifies the supported image-selection procedure;
        # it does not claim a cross-version application downgrade.
        restored.rollback(image)
        self.ready(self.port + 1)
        first = jobs[0]
        assert (
            self.request(
                "/jobs", submitter, body=first["request"], key=first["key"], port=self.port + 1
            )[1]["id"]
            == first["id"]
        )
        assert self.request("/budget", submitter, port=self.port + 1)[1] == budget
        (self.output / "demonstration.json").write_text(
            json.dumps(
                {
                    "label": "VERIFIED",
                    "planned_jobs": 4,
                    "jobs": jobs,
                    "correlation": correlation,
                    "source_state": original,
                    "restored_state_identical": True,
                    "synthetic_effects": effect,
                    "budget": budget,
                    "live_while_db_down": 200,
                    "ready_while_db_down": 503,
                    "restored_project": restored_project,
                    "rollback_scope": "incompatible image refused; matching-image restart verified",
                    "live_provider_calls": 0,
                },
                indent=2,
            )
        )

    def down(self) -> None:
        projects = sorted(self.owned_projects)
        results = []
        for project in projects:
            prefix = [*self.ops.prefix[:-1], project]
            self.record("teardown-" + project, [*prefix, "down", "--remove-orphans"])
            containers = (
                self.record(
                    "remaining-" + project,
                    [
                        "docker",
                        "ps",
                        "-a",
                        "-q",
                        "--filter",
                        "label=com.docker.compose.project=" + project,
                    ],
                )
                .decode()
                .strip()
            )
            assert not containers
            volumes = (
                self.record(
                    "volumes-" + project,
                    [
                        "docker",
                        "volume",
                        "ls",
                        "-q",
                        "--filter",
                        "label=com.docker.compose.project=" + project,
                    ],
                )
                .decode()
                .split()
            )
            results.append(
                {"project": project, "remaining_containers": [], "retained_volumes": volumes}
            )
        (self.output / "teardown.json").write_text(json.dumps(results, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--phase", choices=("all", "build", "tests", "demo", "down"), default="all")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verification = Verification(args.project, args.port, args.output.resolve())
    verification.initialize()
    try:
        if args.phase in ("all", "build"):
            verification.build()
        if args.phase in ("all", "tests"):
            verification.tests()
        if args.phase in ("all", "demo"):
            verification.demo()
        if args.phase == "down":
            verification.selected_image()
    finally:
        if args.phase in ("all", "demo", "down"):
            verification.down()


if __name__ == "__main__":
    main()
