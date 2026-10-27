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
from agent_reliability.workflow.catalog import resolved_payload
from agent_reliability.workflow.migrations import migrate
from agent_reliability.workflow.models import JobRequest, Policy
from agent_reliability.workflow.store import IdempotencyConflict, Store
from agent_reliability.workflow.worker import supervise

ROOT = Path(__file__).resolve().parents[2]
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
    with TestClient(create_app(ROOT, store)) as client:
        response = client.post("/jobs", json={}, headers={"Idempotency-Key": "restart"})
        assert response.status_code == 201
        job = response.json()["id"]
    claim = store.claim("running-during-restart")
    with TestClient(create_app(ROOT, Store(store._url))) as client:
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
    with TestClient(create_app(ROOT, store)) as client:
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
