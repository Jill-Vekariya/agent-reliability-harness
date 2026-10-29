"""Real PostgreSQL semantics. Skipped explicitly when no dedicated test DB is configured."""

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from agent_reliability.workflow.api import create_app
from agent_reliability.workflow.auth import DemoAuth, Principal
from agent_reliability.workflow.catalog import resolved_payload
from agent_reliability.workflow.migrations import migrate
from agent_reliability.workflow.models import JobRequest, Policy
from agent_reliability.workflow.store import IdempotencyConflict, Store
from agent_reliability.workflow.worker import supervise

ROOT = Path(__file__).resolve().parents[2]
AUTH = DemoAuth({"stage1-test-token-000000000000": Principal("local-demo", "test-operator", True)})
HEADERS = {"Authorization": "Bearer stage1-test-token-000000000000"}
URL = os.environ.get("ARH_WORKFLOW_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Requires dedicated ARH_WORKFLOW_TEST_DATABASE_URL; Compose checks supplies one"
)


@pytest.fixture
def store():
    assert URL
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(URL) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    scoped = make_conninfo(URL, options=f"-c search_path={schema}")
    migrate(scoped)
    # Retain uniquely named schemas/failed records; never erase earlier test evidence.
    return Store(scoped, Policy(backoff_seconds=0.02))


def submit(store, **kwargs):
    row, created = store.submit(uuid.uuid4().hex, resolved_payload(ROOT, JobRequest(**kwargs)))
    assert created
    return str(row["id"])


def due(store, job):
    with store.connect() as conn:
        conn.execute("UPDATE workflow_jobs SET next_run_at=clock_timestamp() WHERE id=%s", (job,))


def expire(store, job):
    with store.connect() as conn:
        conn.execute(
            "UPDATE workflow_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (job,),
        )


def test_migration_reentry_and_checksum_guard(store):
    migrate(store._url)
    assert store.ready()
    with store.connect() as conn:
        conn.execute("UPDATE workflow_schema_migrations SET sha256='changed'")
    with pytest.raises(ValueError, match="checksum"):
        migrate(store._url)


def test_admission_is_atomic_and_payload_bound_under_race(store):
    payload = resolved_payload(ROOT, JobRequest())
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda _: store.submit("same-key", payload), range(12)))
    assert sum(created for _, created in values) == 1
    assert len({str(row["id"]) for row, _ in values}) == 1
    with pytest.raises(IdempotencyConflict):
        store.submit("same-key", resolved_payload(ROOT, JobRequest(task_id="q002")))
    assert len(store.list_jobs()) == 1


def test_competing_workers_get_disjoint_claims(store):
    ids = {submit(store) for _ in range(12)}
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda n: store.claim(f"worker-{n}"), range(18)))
    claims = [c for c in claims if c]
    assert {c.job_id for c in claims} == ids
    assert len(claims) == len(ids)
    assert all(store.finish(c, {"ok": True, "worker": c.worker_id}) for c in claims)
    assert store.claim("empty") is None


def test_expired_worker_cannot_renew_or_commit_and_lost_attempt_survives(store):
    job = submit(store)
    first = store.claim("first")
    expire(store, job)
    assert not store.heartbeat(first)
    assert not store.finish(first, {"ok": True, "stale": True})
    assert store.recover() == 1
    due(store, job)
    second = store.claim("second")
    assert second.number == 2 and second.token != first.token
    assert store.finish(second, {"ok": True, "winner": "second"})
    assert not store.finish(first, {"ok": True, "stale": True})
    assert store.get(job)["result"] == {"ok": True, "winner": "second"}
    attempts = store.attempts(job)
    assert [a["state"] for a in attempts] == ["lost", "succeeded"]
    assert attempts[0]["stale_result_rejections"] == 2


def test_result_fence_rechecks_time_after_waiting_for_row_lock(store):
    job = submit(store)
    claim = store.claim("stale")
    with store.connect() as conn:
        conn.execute("SELECT id FROM workflow_jobs WHERE id=%s FOR UPDATE", (job,))
        conn.execute(
            "UPDATE workflow_jobs SET lease_expires_at=clock_timestamp()+interval '100 milliseconds' WHERE id=%s",
            (job,),
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(store.finish, claim, {"ok": True})
            time.sleep(0.2)
            conn.commit()
            assert future.result(timeout=5) is False
    assert store.get(job)["state"] == "running"
    assert store.attempts(job)[0]["result"] is None


def test_retry_limit_retains_every_failed_attempt_and_persisted_policy(store):
    job = submit(store)
    restarted = Store(store._url, Policy(max_attempts=10, attempt_seconds=60))
    for n in range(1, 4):
        claim = restarted.claim("restarted")
        assert claim.number == n and claim.timeout_seconds <= 30
        assert restarted.finish(
            claim, {"ok": False, "error_code": "synthetic_failure", "retryable": True}
        )
        due(store, job) if n < 3 else None
    assert store.get(job)["state"] == "failed"
    assert len(store.attempts(job)) == 3
    assert all(
        a["error_code"] == "synthetic_failure" and a["finished_at"] for a in store.attempts(job)
    )
    assert restarted.claim("no-fourth") is None


def test_permanent_error_does_not_retry(store):
    job = submit(store)
    assert store.finish(
        store.claim("one"), {"ok": False, "error_code": "provenance_changed", "retryable": False}
    )
    assert store.get(job)["state"] == "failed"
    assert len(store.attempts(job)) == 1


def test_lease_recovery_exhausts_attempt_cap(store):
    job = submit(store)
    for n in range(1, 4):
        assert store.claim("crashing").number == n
        expire(store, job)
        store.recover()
        if n < 3:
            due(store, job)
    assert store.get(job)["state"] == "failed"
    assert [a["state"] for a in store.attempts(job)] == ["lost"] * 3


def test_queued_deadline_is_terminal_without_execution(store):
    job = submit(store)
    with store.connect() as conn:
        conn.execute(
            "UPDATE workflow_jobs SET deadline_at=created_at+interval '1 millisecond' WHERE id=%s",
            (job,),
        )
    time.sleep(0.01)
    store.recover()
    row = store.get(job)
    assert row["state"] == "failed" and row["error_code"] == "job_deadline"
    assert not store.attempts(job)


def test_database_rejects_invalid_transitions_and_terminal_rewrite(store):
    job = submit(store)
    with pytest.raises(psycopg.Error, match="transition"):
        with store.connect() as conn:
            conn.execute("UPDATE workflow_jobs SET state='retry_wait' WHERE id=%s", (job,))
    assert store.finish(store.claim("one"), {"ok": True})
    with pytest.raises(psycopg.Error, match="immutable"):
        with store.connect() as conn:
            conn.execute("UPDATE workflow_jobs SET error_code='rewrite' WHERE id=%s", (job,))


def test_api_restart_preserves_identity_status_and_attempts(store):
    with TestClient(create_app(ROOT, store, AUTH), headers=HEADERS) as client:
        response = client.post("/jobs", json={}, headers={"Idempotency-Key": "restart"})
        assert response.status_code == 201
        job = response.json()["id"]
    claim = store.claim("running-during-restart")
    with TestClient(create_app(ROOT, Store(store._url), AUTH), headers=HEADERS) as client:
        assert client.get(f"/jobs/{job}").json()["state"] == "running"
        assert len(client.get(f"/jobs/{job}/attempts").json()) == 1
        assert (
            client.post("/jobs", json={}, headers={"Idempotency-Key": "restart"}).json()["id"]
            == job
        )
        conflict = client.post(
            "/jobs", json={"task_id": "q002"}, headers={"Idempotency-Key": "restart"}
        )
        assert conflict.status_code == 409
        assert "lease_token" not in client.get(f"/jobs/{job}").json()
        assert "token" not in client.get(f"/jobs/{job}/attempts").json()[0]
    assert store.finish(claim, {"ok": True})


def test_api_rejects_unapproved_inputs_and_actual_oversized_body(store):
    with TestClient(create_app(ROOT, store, AUTH), headers=HEADERS) as client:
        for body in [{"sql": "DROP TABLE x"}, {"task_id": "missing"}, {"provider": "openai"}]:
            assert (
                client.post(
                    "/jobs", json=body, headers={"Idempotency-Key": uuid.uuid4().hex}
                ).status_code
                == 422
            )
        assert (
            client.post(
                "/jobs",
                content=b"x" * 5000,
                headers={"content-length": "1", "Idempotency-Key": "large"},
            ).status_code
            == 413
        )
        assert client.get("/jobs?limit=1000").status_code == 422
        assert client.get(f"/jobs/{uuid.uuid4()}").status_code == 404
        assert client.get("/jobs").json() == []


def test_real_fixture_attempt_persists_trace_and_grade(store, tmp_path):
    job = submit(store, task_id="q002")
    claim = store.claim("actual")
    result = supervise(store, claim, ROOT, tmp_path / "effects.sqlite", threading.Event())
    assert result["ok"] and result["grade"]["correct"] is False
    assert store.finish(claim, result)
    assert store.get(job)["result"]["trace"]["attempt_id"] == f"{job}:1"


def test_actual_timeout_is_recorded_as_failed_attempt(store, tmp_path):
    short = Store(store._url, Policy(max_attempts=1, attempt_seconds=1, job_seconds=20))
    job = submit(short, demo="sleep", delay_seconds=5.0)
    claim = short.claim("timeout")
    result = supervise(short, claim, ROOT, tmp_path / "effects.sqlite", threading.Event())
    assert result["error_code"] == "attempt_timeout"
    assert short.finish(claim, result)
    assert short.get(job)["state"] == "failed"
    assert short.attempts(job)[0]["state"] == "timed_out"


# Stage 2 checks retain the Stage 1 tests above and their PostgreSQL fixtures.
A_TOKEN = "tenant-a-submitter-token-000000"
P_TOKEN = "tenant-a-approver-token-0000000"
B_TOKEN = "tenant-b-approver-token-0000000"
CONTROL_AUTH = DemoAuth(
    {
        A_TOKEN: Principal("tenant-a", "alice"),
        P_TOKEN: Principal("tenant-a", "reviewer-a", True),
        B_TOKEN: Principal("tenant-b", "reviewer-b", True),
    }
)


def headers(token):
    return {"Authorization": "Bearer " + token}


def controlled(store, tenant="tenant-a", **kwargs):
    row, _ = store.submit(uuid.uuid4().hex, resolved_payload(ROOT, JobRequest(**kwargs)), tenant)
    return str(row["id"])


def approve(store, job, tenant="tenant-a"):
    approval = next(
        a for a in store.approvals(tenant) if str(a["job_id"]) == job and a["state"] == "pending"
    )
    return store.decide(
        tenant,
        str(approval["id"]),
        "reviewer-a",
        "approved",
        approval["action_hash"],
        approval["action_version"],
    )


def test_authenticated_context_is_required_and_tenant_headers_are_ignored(store):
    with TestClient(create_app(ROOT, store, CONTROL_AUTH)) as client:
        assert client.get("/live").status_code == 200
        for path in ["/jobs", "/approvals", "/budget", f"/jobs/{uuid.uuid4()}"]:
            assert client.get(path).status_code == 401
        assert client.get("/jobs", headers=headers("invalid")).status_code == 401
        response = client.post(
            "/jobs",
            json={},
            headers={**headers(A_TOKEN), "Idempotency-Key": "auth", "X-Tenant-ID": "tenant-b"},
        )
        job = response.json()["id"]
        assert response.status_code == 201
        assert store.get(job, "tenant-a") and store.get(job, "tenant-b") is None
        assert (
            client.post(
                "/jobs",
                json={"tenant_id": "tenant-b"},
                headers={**headers(A_TOKEN), "Idempotency-Key": "forged"},
            ).status_code
            == 422
        )


def test_all_identifier_and_list_search_routes_enforce_tenant_isolation(store):
    job = controlled(store, demo="provider")
    approval = store.approvals("tenant-a")[0]
    store.set_budget("tenant-a", 10)
    with TestClient(create_app(ROOT, store, CONTROL_AUTH)) as client:
        for suffix in ["", "/attempts", "/result", "/trace", "/operations"]:
            assert client.get(f"/jobs/{job}{suffix}", headers=headers(B_TOKEN)).status_code == 404
        assert client.post(f"/jobs/{job}/cancel", headers=headers(B_TOKEN)).status_code == 404
        assert (
            client.get(f"/approvals/{approval['id']}", headers=headers(B_TOKEN)).status_code == 404
        )
        decision = {
            "decision": "approved",
            "action_hash": approval["action_hash"],
            "action_version": 1,
        }
        assert (
            client.post(
                f"/approvals/{approval['id']}/decision", json=decision, headers=headers(B_TOKEN)
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/approvals/{approval['id']}/decision", json=decision, headers=headers(A_TOKEN)
            ).status_code
            == 403
        )
        assert client.get("/approvals", headers=headers(B_TOKEN)).json() == []
        assert client.get("/budget", headers=headers(B_TOKEN)).status_code == 404
        for query in [
            "",
            "?state=waiting_approval",
            "?task_id=q001",
            "?state=waiting_approval&task_id=q001&limit=100",
        ]:
            assert client.get("/jobs" + query, headers=headers(B_TOKEN)).json() == []
        same = client.post(
            "/jobs", json={}, headers={**headers(B_TOKEN), "Idempotency-Key": "same"}
        )
        other = client.post(
            "/jobs", json={}, headers={**headers(A_TOKEN), "Idempotency-Key": "same"}
        )
        assert (
            same.status_code == other.status_code == 201 and same.json()["id"] != other.json()["id"]
        )


def test_api_redacts_sensitive_trace_and_unknown_result_fields(store):
    job = controlled(store)
    claim = store.claim("trace")
    secret = "sensitive-test-content"
    assert store.finish(
        claim,
        {
            "ok": True,
            "secret": secret,
            "trace": {
                "prompt": secret,
                "events": [{"sql": secret, "rows": [secret]}],
                "authorization": secret,
            },
        },
    )
    with TestClient(create_app(ROOT, store, CONTROL_AUTH), headers=headers(A_TOKEN)) as client:
        for path in [
            f"/jobs/{job}",
            f"/jobs/{job}/attempts",
            f"/jobs/{job}/trace",
            f"/jobs/{job}/result",
        ]:
            response = client.get(path)
            assert response.status_code == 200 and secret not in response.text
            assert claim.token not in response.text and "worker_id" not in response.text
        assert client.get(f"/jobs/{job}/result").json()["trace"] == {
            "event_count": 1,
            "redacted": True,
        }
    assert (
        store.get(job, "tenant-a")["result"]["secret"] == secret
    )  # Raw evidence retained privately.


def test_approval_binds_payload_version_role_and_single_attempt_across_restart(store):
    from agent_reliability.workflow.store import ControlConflict

    job = controlled(store, demo="provider")
    assert store.claim("before-decision") is None
    approval = store.approvals("tenant-a")[0]
    for action_hash, version in [("0" * 64, 1), (approval["action_hash"], 2)]:
        with pytest.raises(ControlConflict):
            store.decide(
                "tenant-a", str(approval["id"]), "reviewer-a", "approved", action_hash, version
            )
    restarted = Store(store._url)
    with TestClient(create_app(ROOT, restarted, CONTROL_AUTH), headers=headers(P_TOKEN)) as client:
        decision = {
            "decision": "approved",
            "action_hash": approval["action_hash"],
            "action_version": 1,
        }
        assert (
            client.post(f"/approvals/{approval['id']}/decision", json=decision).status_code == 200
        )
        assert (
            client.post(f"/approvals/{approval['id']}/decision", json=decision).status_code == 409
        )
    claim = Store(store._url).claim("after-restart")
    assert claim and claim.job_id == job and claim.tenant_id == "tenant-a"
    assert store.approvals("tenant-a")[0]["state"] == "consumed"
    assert store.approvals("tenant-a")[0]["approver"] == "reviewer-a"
    assert store.finish(claim, {"ok": False, "retryable": True})
    assert store.get(job, "tenant-a")["state"] == "waiting_approval"
    assert store.claim("no-reused-approval") is None
    second = next(a for a in store.approvals("tenant-a") if a["state"] == "pending")
    assert second["attempt_number"] == 2 and second["id"] != approval["id"]
    with pytest.raises(psycopg.Error, match="immutable"):
        with store.connect() as conn:
            conn.execute("UPDATE workflow_jobs SET action_version=2 WHERE id=%s", (job,))


@pytest.mark.parametrize("approved", [False, True])
def test_expired_approval_cannot_dispatch(store, approved):
    job = controlled(store, demo="provider")
    if approved:
        approve(store, job)
    with store.connect() as conn:
        conn.execute(
            "UPDATE workflow_approvals SET expires_at=clock_timestamp()-interval '1 second' WHERE job_id=%s",
            (job,),
        )
    assert Store(store._url).claim("expired") is None
    assert store.get(job, "tenant-a")["error_code"] == "approval_expired"
    assert store.approvals("tenant-a")[0]["state"] == "expired"
    assert not store.attempts(job, "tenant-a")


def test_rejection_is_persisted_and_never_claimed(store):
    job = controlled(store, require_approval=True)
    a = store.approvals("tenant-a")[0]
    store.decide("tenant-a", str(a["id"]), "reviewer-a", "rejected", a["action_hash"], 1)
    assert Store(store._url).claim("rejected") is None
    assert store.get(job, "tenant-a")["error_code"] == "approval_rejected"
    assert Store(store._url).approvals("tenant-a")[0]["approver"] == "reviewer-a"


@pytest.mark.parametrize("waiting", [False, True])
def test_cancellation_prevents_claim_and_is_repeatable(store, waiting):
    job = controlled(store, require_approval=waiting)
    row = store.cancel(job, "tenant-a", "alice")
    assert row["state"] == "cancelled" and row["cancel_requested_at"]
    assert store.cancel(job, "tenant-a", "alice")["state"] == "cancelled"
    assert Store(store._url).claim("after-cancel") is None
    assert not store.attempts(job, "tenant-a")


def test_completion_and_cancellation_serialize_without_losing_running_result(store):
    from agent_reliability.workflow.store import ControlConflict

    for _ in range(8):
        job = controlled(store)
        claim = store.claim("race")
        barrier = threading.Barrier(2)

        def cancel_race(barrier=barrier, job=job):
            barrier.wait()
            try:
                return store.cancel(job, "tenant-a", "alice")["state"]
            except ControlConflict:
                return "too_late"

        def complete_race(barrier=barrier, claim=claim):
            barrier.wait()
            return store.finish(claim, {"ok": True, "completed_operation": True})

        with ThreadPoolExecutor(max_workers=2) as pool:
            cancelled = pool.submit(cancel_race)
            finished = pool.submit(complete_race)
            assert finished.result(timeout=5)
            outcome = cancelled.result(timeout=5)
        row = store.get(job, "tenant-a")
        assert row["state"] == ("succeeded" if outcome == "too_late" else "cancelled")
        assert store.attempts(job, "tenant-a")[0]["result"]["completed_operation"]


def test_shared_budget_concurrency_never_overreserves(store):
    from agent_reliability.workflow.store import ControlConflict

    store.set_budget("tenant-a", 10)
    jobs = [controlled(store, demo="provider") for _ in range(2)]
    for job in jobs:
        approve(store, job)
    claims = [store.claim("budget-" + str(n)) for n in range(2)]

    def reserve(claim):
        try:
            return store.reserve(claim, 10)
        except ControlConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, claims))
    assert sum(r is not None for r in results) == 1
    assert store.budget("tenant-a")["reserved_units"] == 10
    winner = next((c, op) for c, op in zip(claims, results, strict=True) if op)
    claim, operation = winner
    with pytest.raises(ControlConflict):
        store.reserve(claim, 10)
    assert store.dispatch(claim, operation)
    assert not store.dispatch(claim, operation)
    assert store.settle(claim, operation, 6)
    assert not store.settle(claim, operation, 6)
    assert store.budget("tenant-a")["reserved_units"] == 0
    assert store.budget("tenant-a")["spent_units"] == 6


@pytest.mark.parametrize("dispatched", [False, True])
def test_crash_recovery_releases_only_known_undispatched_reservations(store, dispatched):
    store.set_budget("tenant-a", 10)
    job = controlled(store, demo="provider")
    approve(store, job)
    claim = store.claim("crashed")
    operation = store.reserve(claim, 10)
    if dispatched:
        assert store.dispatch(claim, operation)
    expire(store, job)
    Store(store._url).recover()
    assert store.get(job, "tenant-a")["state"] == "waiting_approval"
    op = store.operations(job, "tenant-a")[0]
    assert op["state"] == ("uncertain" if dispatched else "released")
    assert store.budget("tenant-a")["reserved_units"] == (10 if dispatched else 0)
    assert not store.dispatch(claim, operation)
    assert not store.finish(claim, {"ok": True})
    if dispatched:
        assert store.settle(claim, operation, 6)  # Late known billing, no job result authority.
        assert store.get(job, "tenant-a")["state"] == "waiting_approval"


def test_running_cancellation_keeps_uncertain_cost_and_late_operation_outcome(store):
    store.set_budget("tenant-a", 10)
    job = controlled(store, demo="provider")
    approve(store, job)
    claim = store.claim("in-flight")
    operation = store.reserve(claim, 10)
    assert store.dispatch(claim, operation)
    assert store.cancel(job, "tenant-a", "alice")["state"] == "running"
    assert not store.heartbeat(claim)
    assert store.finish(claim, {"ok": False, "error_code": "lease_lost"})
    assert store.get(job, "tenant-a")["state"] == "cancelled"
    assert store.operations(job, "tenant-a")[0]["state"] == "uncertain"
    assert store.budget("tenant-a")["reserved_units"] == 10
    assert store.settle(claim, operation, 6)
    assert store.operations(job, "tenant-a")[0]["state"] == "succeeded"
    assert store.get(job, "tenant-a")["state"] == "cancelled"


def test_cancellation_before_dispatch_releases_reservation_without_provider_call(store):
    store.set_budget("tenant-a", 10)
    job = controlled(store, demo="provider")
    approve(store, job)
    claim = store.claim("reserved")
    operation = store.reserve(claim, 10)
    store.cancel(job, "tenant-a", "alice")
    assert not store.dispatch(claim, operation)
    assert store.finish(claim, {"ok": False, "error_code": "dispatch_not_authorized"})
    assert store.operations(job, "tenant-a")[0]["state"] == "released"
    assert store.budget("tenant-a")["reserved_units"] == 0


@pytest.mark.parametrize("usage", ["known", "missing_usage", "missing_price"])
def test_deterministic_fake_provider_accounts_usage_conservatively(store, tmp_path, usage):
    from agent_reliability.workflow.worker import run_attempt

    store.set_budget("tenant-a", 10)
    job = controlled(store, demo="provider", fake_usage=usage)
    approve(store, job)
    restarted = Store(store._url)
    claim = restarted.claim("fake")
    result = run_attempt(restarted, claim, ROOT, tmp_path / "effects.sqlite", threading.Event())
    assert restarted.finish(claim, result)
    budget = store.budget("tenant-a")
    if usage == "missing_price":
        assert result["error_code"] == "pricing_unknown"
        assert not store.operations(job, "tenant-a")
        assert budget["spent_units"] == budget["reserved_units"] == 0
    elif usage == "missing_usage":
        assert result["ok"]
        assert budget["reserved_units"] == 10 and budget["spent_units"] == 0
        assert store.operations(job, "tenant-a")[0]["state"] == "uncertain"
    else:
        assert result["ok"]
        assert budget["reserved_units"] == 0 and budget["spent_units"] == 6
        assert store.operations(job, "tenant-a")[0]["state"] == "succeeded"


def test_real_api_and_worker_process_restarts_preserve_approvals_and_uncertain_cost(
    store, tmp_path
):
    """Real processes and PostgreSQL; synthetic provider, no external side effects."""
    import json
    import socket
    import subprocess
    import sys

    import httpx

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "ARH_TEST_SCOPED_DB": store._url,
        "ARH_TEST_ROOT": str(ROOT),
        "ARH_TEST_PORT": str(port),
        "ARH_TEST_EFFECTS": str(tmp_path / "effects.sqlite"),
        "ARH_WORKFLOW_AUTH_JSON": json.dumps(
            {P_TOKEN: {"tenant_id": "tenant-a", "subject": "reviewer-a", "can_approve": True}}
        ),
    }
    env.pop("ARH_WORKFLOW_AUTH_FILE", None)
    api_code = """
import os
from pathlib import Path
import uvicorn
from agent_reliability.workflow.api import create_app
from agent_reliability.workflow.store import Store
uvicorn.run(create_app(Path(os.environ['ARH_TEST_ROOT']), Store(os.environ['ARH_TEST_SCOPED_DB'])), host='127.0.0.1', port=int(os.environ['ARH_TEST_PORT']), access_log=False, proxy_headers=False, log_level='error')
"""
    worker_code = """
import os
from pathlib import Path
from agent_reliability.workflow.worker import run_worker
from agent_reliability.workflow.store import Store
from agent_reliability.workflow.models import Policy
run_worker(Store(os.environ['ARH_TEST_SCOPED_DB'], Policy(lease_seconds=2,heartbeat_seconds=0.2,poll_seconds=0.05,backoff_seconds=0.02)), Path(os.environ['ARH_TEST_ROOT']), 'restart-process', Path(os.environ['ARH_TEST_EFFECTS']))
"""
    processes = []
    active = {}

    def spawn(code, role):
        log = tmp_path / f"{len(processes):02d}-{role}.log"
        with log.open("xb") as stream:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", code],
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        processes.append(proc)
        active[role] = (proc, log)
        return proc

    def until(check, stage, seconds=12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            for role, (proc, log) in active.items():
                assert proc.poll() is None, (
                    f"{stage}: {role} exited with {proc.returncode}; retained log: {log}"
                )
            try:
                value = check()
                if value:
                    return value
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        raise AssertionError(
            f"Bounded process-restart observation timed out at {stage}; logs retained in {tmp_path}"
        )

    try:
        store.set_budget("tenant-a", 20)
        with httpx.Client(
            base_url=base, headers=headers(P_TOKEN), trust_env=False, timeout=1
        ) as client:
            api = spawn(api_code, "api")
            until(lambda: client.get("/ready").status_code == 200, "initial API readiness")
            response = client.post(
                "/jobs",
                json={"demo": "provider", "delay_seconds": 3},
                headers={"Idempotency-Key": "process-restart"},
            )
            assert response.status_code == 201
            job = response.json()["id"]
            api.terminate()
            api.wait(timeout=3)
            worker = spawn(worker_code, "worker")
            assert store.get(job, "tenant-a")["state"] == "waiting_approval"
            api = spawn(api_code, "api")
            until(lambda: client.get("/ready").status_code == 200, "restarted API readiness")
            approval = next(a for a in client.get("/approvals").json() if a["job_id"] == job)
            decision = {
                "decision": "approved",
                "action_hash": approval["action_hash"],
                "action_version": 1,
            }
            assert (
                client.post(f"/approvals/{approval['id']}/decision", json=decision).status_code
                == 200
            )
            until(
                lambda: any(o["state"] == "in_flight" for o in store.operations(job, "tenant-a")),
                "provider reservation and dispatch",
            )
            worker.kill()
            worker.wait(timeout=3)
            expire(store, job)  # Deterministic crash injection; avoids wall-clock lease sleeps.
            worker = spawn(worker_code, "worker")
            until(
                lambda: store.get(job, "tenant-a")["state"] == "waiting_approval", "lease recovery"
            )
            assert store.operations(job, "tenant-a")[0]["state"] == "uncertain"
            assert store.budget("tenant-a")["reserved_units"] == 10
            approval = next(
                a
                for a in client.get("/approvals").json()
                if a["job_id"] == job and a["state"] == "pending"
            )
            assert approval["attempt_number"] == 2
            assert (
                client.post(f"/approvals/{approval['id']}/decision", json=decision).status_code
                == 200
            )
            until(
                lambda: store.get(job, "tenant-a")["state"] == "succeeded",
                "approved retry completion",
            )
            api.terminate()
            api.wait(timeout=3)
            api = spawn(api_code, "api")
            until(lambda: client.get("/ready").status_code == 200, "final API readiness")
            # A restarted API has no one-second latency SLA. Keep the existing
            # request timeout and bounded reconnect window; inspect the first
            # returned response so wrong HTTP/status/data cannot be polled away.
            observed = until(lambda: client.get(f"/jobs/{job}"), "persisted result read")
            assert observed.status_code == 200
            assert observed.json()["state"] == "succeeded"
            assert [a["state"] for a in store.attempts(job, "tenant-a")] == ["lost", "succeeded"]
            assert [o["state"] for o in store.operations(job, "tenant-a")] == [
                "uncertain",
                "succeeded",
            ]
            assert store.budget("tenant-a")["spent_units"] == 6
            assert store.budget("tenant-a")["reserved_units"] == 10
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
