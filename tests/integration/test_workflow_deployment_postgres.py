"""Real persisted correlation, tenant metrics and migration readiness."""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from agent_reliability.workflow.api import create_app
from agent_reliability.workflow.auth import DemoAuth, Principal
from agent_reliability.workflow.catalog import resolved_payload
from agent_reliability.workflow.models import JobRequest
from tests.integration import test_workflow_postgres as postgres_tests

ROOT, URL = postgres_tests.ROOT, postgres_tests.URL
deployment_store = postgres_tests.store

pytestmark = pytest.mark.skipif(not URL, reason="Requires dedicated ARH_WORKFLOW_TEST_DATABASE_URL")


def test_persisted_request_context_does_not_change_idempotency(deployment_store):
    store = deployment_store
    token = "deployment-real-test-token-00000000"
    auth = DemoAuth({token: Principal("tenant-a", "operator")})
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": "same-action"}
    with TestClient(create_app(ROOT, store, auth)) as client:
        first = client.post("/jobs", json={"task_id": "q001"}, headers=headers)
        second = client.post("/jobs", json={"task_id": "q001"}, headers=headers)
        assert first.status_code == 201 and second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        row = store.get(first.json()["id"], "tenant-a")
        assert row["request_id"] == first.headers["X-Request-ID"]
        assert row["trace_id"] == first.headers["X-Trace-ID"]
        assert row["trace_id"] != second.headers["X-Trace-ID"]
        store.submit(uuid.uuid4().hex, resolved_payload(ROOT, JobRequest()), "tenant-b")
        metrics = client.get("/metrics", headers=headers)
        assert 'arh_workflow_jobs{state="queued"} 1' in metrics.text
        claim = store.claim("deployment-worker")
        assert claim and claim.request_id == row["request_id"] and claim.trace_id == row["trace_id"]


def test_readiness_rejects_checksum_drift_and_context_is_immutable(deployment_store):
    store = deployment_store
    row, _ = store.submit("context", resolved_payload(ROOT, JobRequest()), request_id="a" * 32)
    with pytest.raises(psycopg.errors.RaiseException, match="observability context"):
        with store.connect() as conn:
            conn.execute(
                "UPDATE workflow_jobs SET request_id=%s WHERE id=%s", ("b" * 32, row["id"])
            )
    with store.connect() as conn:
        conn.execute("UPDATE workflow_schema_migrations SET sha256='drift'")
    assert not store.ready()
