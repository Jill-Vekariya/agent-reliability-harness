"""Predeclared, bounded synthetic workflow measurement; retains every planned batch."""

import argparse
import json
import os
import platform
import random
import resource
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from agent_reliability.evaluation.review import check_reviews, review_packet
from agent_reliability.evaluation.statistics import quantile
from agent_reliability.util import canonical, digest, file_hash
from agent_reliability.workflow.api import attempt_view, create_app, job_view
from agent_reliability.workflow.auth import DemoAuth, Principal
from agent_reliability.workflow.catalog import resolved_payload
from agent_reliability.workflow.migrations import migrate
from agent_reliability.workflow.models import TERMINAL, JobRequest, Policy
from agent_reliability.workflow.store import Store

ROOT = Path(__file__).resolve().parents[1]
WORKER_CODE = """
import os, logging
from pathlib import Path
logging.basicConfig(level=logging.INFO, format="%(message)s")
from agent_reliability.workflow.models import Policy
from agent_reliability.workflow.store import Store
from agent_reliability.workflow.worker import run_worker
run_worker(Store(os.environ['ARH_MEASURE_DB'], Policy(**__import__('json').loads(os.environ['ARH_MEASURE_POLICY']))), Path(os.environ['ARH_MEASURE_ROOT']), os.environ['ARH_MEASURE_WORKER'], Path(os.environ['ARH_MEASURE_EFFECTS']))
"""


def summarize(
    jobs: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    budget: dict[str, Any] | None,
    planned: int,
) -> dict[str, Any]:
    """Execution denominators retain planned/unstarted work and intentional failures."""
    states = Counter(j["state"] for j in jobs)
    terminal = sum(v for k, v in states.items() if k in TERMINAL)
    waits = [
        (a["started_at"] - j["created_at"]).total_seconds()
        for j in jobs
        for a in attempts
        if a["job_id"] == j["id"] and a["number"] == 1
    ]
    latencies = [
        (j["finished_at"] - j["created_at"]).total_seconds() for j in jobs if j["finished_at"]
    ]
    grades = [
        j["result"]["grade"]["correct"] for j in jobs if j.get("result") and "grade" in j["result"]
    ]
    held = sum(
        o["reserved_units"]
        for o in operations
        if o["state"] in {"reserved", "in_flight", "uncertain"}
    )
    spent = sum(o["actual_units"] for o in operations if o["state"] == "succeeded")
    return {
        "planned_jobs": planned,
        "admitted_jobs": len(jobs),
        "never_admitted": planned - len(jobs),
        "terminal_jobs": terminal,
        "nonterminal_jobs": len(jobs) - terminal,
        "terminal_coverage": terminal / planned if planned else None,
        "states": dict(states),
        "succeeded_over_planned": states["succeeded"] / planned if planned else None,
        "attempts": len(attempts),
        "retried_jobs": sum(j["attempt_count"] > 1 for j in jobs),
        "extra_attempts": sum(max(0, j["attempt_count"] - 1) for j in jobs),
        "attempt_states": dict(Counter(a["state"] for a in attempts)),
        "queue_wait_seconds": {
            "count": len(waits),
            "median": quantile(waits, 0.5),
            "p95": quantile(waits, 0.95),
        },
        "terminal_latency_seconds": {
            "count": len(latencies),
            "median": quantile(latencies, 0.5),
            "p95": quantile(latencies, 0.95),
        },
        "latency_limit": "Includes all terminal states; never-admitted/nonterminal work stays in coverage denominators, not fabricated latency values",
        "fixture_grade": {
            "observed": len(grades),
            "correct": sum(grades),
            "incorrect": len(grades) - sum(grades),
            "interpretation": "Exposed deterministic fixture behavior; not measured live model quality",
        },
        "budget_conservation_errors": int(
            budget is None or budget["reserved_units"] != held or budget["spent_units"] != spent
        ),
        "budget_reserved": None if budget is None else budget["reserved_units"],
        "budget_spent": None if budget is None else budget["spent_units"],
    }


def paired_analysis(batches: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: dict[int, dict[str, Any]] = {}
    for batch in batches:
        pairs.setdefault(batch["seed"], {})[batch["arm"]] = batch
    complete = [
        v
        for v in pairs.values()
        if set(v) == {"no_fault", "worker_loss"}
        and all(b.get("label") == "VERIFIED" for b in v.values())
    ]
    if len(complete) != 3:
        return {
            "label": "PARTIALLY VERIFIED",
            "matched_complete_batches": len(complete),
            "incomplete_pairs": len(pairs) - len(complete),
            "effect": None,
            "reason": "Incomplete or failed batches suppress the paired performance comparison; failures remain in raw results",
        }
    differences = [
        p["worker_loss"]["metrics"]["terminal_latency_seconds"]["median"]
        - p["no_fault"]["metrics"]["terminal_latency_seconds"]["median"]
        for p in complete
    ]
    rng = random.Random(1729)
    samples = [
        sum(rng.choices(differences, k=len(differences))) / len(differences) for _ in range(2000)
    ]
    return {
        "label": "VERIFIED",
        "matched_complete_batches": len(complete),
        "mean_paired_median_latency_difference_seconds": sum(differences) / len(differences),
        "exploratory_batch_bootstrap_ci95": [quantile(samples, 0.025), quantile(samples, 0.975)],
        "seed": 1729,
        "resamples": 2000,
        "limitation": "Only three dependent-workload batch pairs on one host; exploratory interval is coarse and supports no production/population performance claim",
    }


def run_batch(
    url: str, protocol: dict[str, Any], arm: str, seed: int, directory: Path, save: Any
) -> dict[str, Any]:
    directory.mkdir()
    schema = "measure_" + uuid.uuid4().hex
    batch: dict[str, Any] = {
        "arm": arm,
        "seed": seed,
        "schema": schema,
        "label": "RUNNING",
        "planned_jobs": len(protocol["workload"]),
        "jobs": [],
        "approvals": [],
        "observations": [],
    }

    def persist() -> None:
        (directory / "batch.json").write_text(json.dumps(batch, indent=2, default=str) + "\n")
        save(batch)

    persist()
    with psycopg.connect(url) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(url, options=f"-c search_path={schema}")
    migrate(scoped)
    policy = Policy(
        max_attempts=protocol["maximum_attempts"],
        attempt_seconds=protocol["attempt_seconds"],
        job_seconds=protocol["job_seconds"],
        lease_seconds=protocol["lease_seconds"],
        heartbeat_seconds=protocol["heartbeat_seconds"],
        poll_seconds=0.1,
        backoff_seconds=0.05,
    )
    store = Store(scoped, policy)
    store.set_budget("measurement", protocol["fake_credit_limit_per_batch"])
    workload = protocol["workload"].copy()
    random.Random(seed).shuffle(workload)
    job_ids: dict[str, str] = {}
    unauthorized: list[dict[str, Any]] = []
    effects = directory / "effects.sqlite"
    processes: dict[str, subprocess.Popen[bytes]] = {}
    logs = []

    def spawn(name: str) -> None:
        stream = (directory / (name + "-" + uuid.uuid4().hex[:8] + ".log")).open("wb")
        logs.append(stream)
        env = {
            **os.environ,
            "ARH_MEASURE_DB": scoped,
            "ARH_MEASURE_POLICY": canonical(policy.__dict__),
            "ARH_MEASURE_ROOT": str(ROOT),
            "ARH_MEASURE_WORKER": name,
            "ARH_MEASURE_EFFECTS": str(effects),
        }
        processes[name] = subprocess.Popen(
            [sys.executable, "-I", "-c", WORKER_CODE], env=env, stdout=stream, stderr=stream
        )

    def approve_pending() -> None:
        approvals = store.approvals("measurement")
        for approval in approvals:
            if approval["state"] == "pending":
                if (
                    approval["action_hash"]
                    != store.get(str(approval["job_id"]), "measurement")["payload_hash"]
                ):
                    raise RuntimeError("Approval payload binding changed")
                decision = store.decide(
                    "measurement",
                    str(approval["id"]),
                    "automated-synthetic-reviewer",
                    "approved",
                    approval["action_hash"],
                    approval["action_version"],
                )
                batch["approvals"].append(
                    {
                        "id": str(approval["id"]),
                        "attempt": approval["attempt_number"],
                        "actor": "automated-synthetic-reviewer",
                        "state": decision["state"],
                    }
                )

    def admit(spec: dict[str, Any]) -> None:
        request = JobRequest(**{k: v for k, v in spec.items() if k != "name"})
        row, _ = store.submit(spec["name"], resolved_payload(ROOT, request), "measurement")
        job_ids[spec["name"]] = str(row["id"])
        batch["jobs"].append(
            {"name": spec["name"], "job_id": str(row["id"]), "request": request.model_dump()}
        )
        persist()
        if spec["name"] != "cancel_queued":
            approve_pending()

    started = time.monotonic()
    usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    killed = False
    fault_time = None
    try:
        cancelled_spec = next(spec for spec in workload if spec["name"] == "cancel_queued")
        admit(cancelled_spec)
        store.cancel(job_ids["cancel_queued"], "measurement", "synthetic-driver")
        for n in range(protocol["workers_per_batch"]):
            spawn("measurement-worker-" + str(n))
        batch["workers_started_at_elapsed_seconds"] = time.monotonic() - started
        admission_started = time.monotonic()
        for spec in workload:
            if spec["name"] not in {"cancel_queued", "effect"}:
                admit(spec)
        admit(next(spec for spec in workload if spec["name"] == "effect"))
        batch["admission_seconds"] = time.monotonic() - admission_started
        batch["driver_preobservation_seconds"] = time.monotonic() - started
        while time.monotonic() - started < protocol["trial_stop_seconds"]:
            approve_pending()
            if arm == "worker_loss" and not killed and effects.exists():
                try:
                    with sqlite3.connect("file:" + str(effects) + "?mode=ro", uri=True) as sink:
                        count = sink.execute(
                            "SELECT count(*) FROM effects WHERE id=?", (job_ids["effect"],)
                        ).fetchone()[0]
                except sqlite3.OperationalError:
                    count = (
                        0  # Sink may be between file creation and committed schema initialization.
                    )
                if count:
                    attempt = store.attempts(job_ids["effect"], "measurement")[-1]
                    if attempt["state"] != "running":
                        raise RuntimeError("Missed declared fault window; retain failed batch")
                    processes[attempt["worker_id"]].kill()
                    processes[attempt["worker_id"]].wait(timeout=3)
                    fault_time = time.monotonic()
                    batch["fault"] = {
                        "kind": "SIGKILL",
                        "job_id": job_ids["effect"],
                        "worker_id": attempt["worker_id"],
                        "elapsed_seconds": fault_time - started,
                        "observed_at": datetime.now(UTC).isoformat(),
                    }
                    spawn(attempt["worker_id"])
                    killed = True
            jobs = store.list_jobs(100, "measurement")
            if (
                fault_time
                and "recovery_seconds" not in batch
                and any(a["number"] > 1 for a in store.attempts(job_ids["effect"], "measurement"))
            ):
                batch["recovery_seconds"] = time.monotonic() - fault_time
            if all(j["state"] in TERMINAL for j in jobs):
                break
            failed_workers = [name for name, p in processes.items() if p.poll() is not None]
            if failed_workers:
                raise RuntimeError("Unexpected worker exit: " + ",".join(failed_workers))
            time.sleep(0.1)
        else:
            batch["stop_reason"] = "60-second batch stopping condition reached"
    finally:
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        for stream in logs:
            stream.close()
        batch["elapsed_seconds"] = time.monotonic() - started
        if "effect" in job_ids:
            tenant_token = "measurement-other-tenant-0000000"
            auth = DemoAuth({tenant_token: Principal("other-tenant", "attacker", True)})
            unauthorized = []
            with TestClient(create_app(ROOT, store, auth)) as client:
                h = {"Authorization": "Bearer " + tenant_token}
                for suffix in ["", "/attempts", "/result", "/trace", "/operations"]:
                    response = client.get(f"/jobs/{job_ids['effect']}{suffix}", headers=h)
                    unauthorized.append(
                        {"path": "job" + suffix, "status": response.status_code, "expected": 404}
                    )
                for path in [
                    "/jobs",
                    "/jobs?task_id=q001",
                    "/jobs?state=waiting_approval",
                    "/approvals",
                ]:
                    response = client.get(path, headers=h)
                    unauthorized.append(
                        {
                            "path": path,
                            "status": response.status_code,
                            "empty": response.json() == [],
                            "expected": 200,
                        }
                    )
            batch["unauthorized_checks"] = unauthorized
        usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        batch["resources"] = {
            "child_user_cpu_seconds": usage_after.ru_utime - usage_before.ru_utime,
            "child_system_cpu_seconds": usage_after.ru_stime - usage_before.ru_stime,
            "max_child_rss_kib": usage_after.ru_maxrss,
            "limit": "Process RUSAGE maximum across reaped children so far, not summed/concurrent/container RSS",
        }
        jobs = [store.get(j, "measurement") for j in job_ids.values()]
        attempts = [a for j in job_ids.values() for a in store.attempts(j, "measurement")]
        operations = [o for j in job_ids.values() for o in store.operations(j, "measurement")]
        budget = store.budget("measurement")
        batch["metrics"] = summarize(jobs, attempts, operations, budget, len(protocol["workload"]))
        batch["job_records"] = [job_view(j) for j in jobs]
        batch["attempt_records"] = [attempt_view(a) for a in attempts]
        batch["operation_records"] = operations
        if effects.exists():
            with sqlite3.connect("file:" + str(effects) + "?mode=ro", uri=True) as sink:
                batch["effect_sink"] = {
                    "committed_effects": sink.execute("SELECT count(*) FROM effects").fetchone()[0],
                    "invocations": sink.execute("SELECT count(*) FROM invocations").fetchone()[0],
                }
        batch["metrics"]["duplicate_committed_effects"] = max(
            0, batch.get("effect_sink", {}).get("committed_effects", 0) - 1
        )
        batch["metrics"]["effect_invocations"] = batch.get("effect_sink", {}).get("invocations")
        m = batch["metrics"]
        invariants = {
            "complete_terminal_coverage": m["terminal_jobs"] == 12,
            "expected_states": m["states"] == {"succeeded": 9, "failed": 2, "cancelled": 1},
            "single_committed_effect": batch.get("effect_sink", {}).get("committed_effects") == 1,
            "no_budget_accounting_error": m["budget_conservation_errors"] == 0,
            "tenant_isolation": len(unauthorized) == 9
            and all(o["status"] == o["expected"] and o.get("empty", True) for o in unauthorized),
            "injected_loss_retained": arm == "no_fault"
            or (killed and m["attempt_states"].get("lost", 0) >= 1 and "recovery_seconds" in batch),
        }
        batch["invariants"] = invariants
        batch["label"] = (
            "VERIFIED" if all(invariants.values()) and "stop_reason" not in batch else "FAILED"
        )
        persist()
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "experiments/workflow-stage3.v2.protocol.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--source-context", type=Path, help="Host Git/source manifest for a container without Git"
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(args.protocol.read_text())
    if (
        protocol.get("driver_version") != "workers_active_during_admission_v2"
        or protocol["planned_jobs"] != 72
        or protocol["jobs_per_batch"] != 12
        or protocol["total_stop_seconds"] > 480
    ):
        raise ValueError("Unsupported/unbounded protocol")
    source_hash = digest(
        {p.relative_to(ROOT).as_posix(): file_hash(p) for p in sorted((ROOT / "src").rglob("*.py"))}
    )
    lock_hash = file_hash(ROOT / "uv.lock")
    if args.source_context:
        context = json.loads(args.source_context.read_text())
        if (
            context["source_sha256"] != source_hash
            or context["dependency_lock_sha256"] != lock_hash
            or context["script_sha256"] != file_hash(Path(__file__))
            or context["protocol_sha256"] != file_hash(args.protocol)
        ):
            raise ValueError("Source context does not match executed source/script/protocol")
        revision, dirty = context["revision"], context["dirty"]
    else:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    import agent_reliability

    installed = Path(agent_reliability.__file__).resolve().parent
    if any(
        file_hash(p) != file_hash(installed / p.relative_to(ROOT / "src/agent_reliability"))
        for p in (ROOT / "src/agent_reliability").rglob("*.py")
    ):
        raise ValueError("Installed runtime differs from measured checkout")
    report: dict[str, Any] = {
        "label": "UNVERIFIED",
        "started_at": datetime.now(UTC).isoformat(),
        "protocol": protocol,
        "protocol_sha256": file_hash(args.protocol),
        "revision": revision,
        "dirty": dirty,
        "source_sha256": source_hash,
        "dependency_lock_sha256": lock_hash,
        "measurement_script_sha256": file_hash(Path(__file__)),
        "environment": platform.platform(),
        "python": sys.version,
        "planned_jobs": 72,
        "batches": [],
    }

    def save(batch: dict[str, Any] | None = None) -> None:
        if batch is not None:
            old = [
                b
                for b in report["batches"]
                if (b["seed"], b["arm"]) != (batch["seed"], batch["arm"])
            ]
            report["batches"] = old + [batch]
        (output / "measurement.json").write_text(json.dumps(report, indent=2, default=str) + "\n")

    save()
    packet = review_packet(ROOT)
    (output / "review-packet.json").write_text(json.dumps(packet, indent=2) + "\n")
    exposure = json.loads((ROOT / "tasks/development_exposure.json").read_text())
    report["label_review"] = {
        "review": check_reviews(ROOT, packet),
        "development_exposed_tasks": len(exposure["task_ids"]),
        "validation_tasks": 0,
        "genuinely_unexposed_test_tasks": 0,
        "label": "BLOCKED",
        "reason": "Independent task-label review and genuinely unexposed new families are unavailable; no tasks are promoted or relabelled as holdout",
    }
    url = os.environ.get("ARH_WORKFLOW_TEST_DATABASE_URL")
    if not url:
        report.update(
            label="BLOCKED",
            reason="Dedicated ARH_WORKFLOW_TEST_DATABASE_URL required; no synthetic measurement was executed",
            never_admitted_jobs=72,
        )
        save()
        raise SystemExit(2)
    start = time.monotonic()
    for index, seed in enumerate(protocol["seeds"]):
        arms = protocol["arms"] if index % 2 == 0 else list(reversed(protocol["arms"]))
        for arm in arms:
            if time.monotonic() - start >= protocol["total_stop_seconds"]:
                report["stop_reason"] = "480-second overall stopping condition reached"
                break
            try:
                run_batch(url, protocol, arm, seed, output / f"{seed}-{arm}", save)
            except Exception as exc:
                # Keep diagnostic class only: connection errors can contain DSN details.
                report["failures"] = report.get("failures", []) + [
                    {"seed": seed, "arm": arm, "diagnostic_type": type(exc).__name__}
                ]
                for batch in report["batches"]:
                    if batch["seed"] == seed and batch["arm"] == arm:
                        batch["label"] = "FAILED"
            save()
    report["analysis"] = paired_analysis(report["batches"])
    report["unstarted_batches"] = 6 - len(report["batches"])
    report["admitted_jobs"] = sum(len(b.get("jobs", [])) for b in report["batches"])
    report["observed_terminal_jobs"] = sum(
        b.get("metrics", {}).get("terminal_jobs", 0) for b in report["batches"]
    )
    report["never_admitted_jobs"] = 72 - report["admitted_jobs"]
    report["unresolved_admitted_jobs"] = report["admitted_jobs"] - report["observed_terminal_jobs"]
    report["label"] = (
        "VERIFIED"
        if len(report["batches"]) == 6 and all(b["label"] == "VERIFIED" for b in report["batches"])
        else "FAILED"
    )
    report["finished_at"] = datetime.now(UTC).isoformat()
    save()
    print(
        json.dumps(
            {
                "label": report["label"],
                "batches": len(report["batches"]),
                "planned_jobs": 72,
                "label_review": "BLOCKED",
                "output": str(output),
            }
        )
    )
    raise SystemExit(0 if report["label"] == "VERIFIED" else 1)


if __name__ == "__main__":
    main()
