"""Boundary and real child-process tests without a PostgreSQL dependency."""

import json
import os
import sqlite3
import threading
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
from agent_reliability.util import digest
from agent_reliability.workflow.catalog import resolved_payload
from agent_reliability.workflow.executor import execute, synthetic_effect
from agent_reliability.workflow.models import JobRequest, Policy, backoff, database_url
from agent_reliability.workflow.store import Claim
from agent_reliability.workflow.worker import child_environment, supervise

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "fields",
    [
        {"max_attempts": 0},
        {"max_attempts": True},
        {"job_seconds": float("inf")},
        {"attempt_seconds": 0.5},
        {"lease_seconds": 0.5},
        {"heartbeat_seconds": 10},
        {"backoff_seconds": 6},
    ],
)
def test_invalid_policy_fails_before_startup(fields):
    with pytest.raises(ValueError):
        Policy(**fields)


def test_default_policy_and_capped_backoff():
    p = Policy()
    assert p.max_attempts == 3 and p.heartbeat_seconds * 2 <= p.lease_seconds
    assert [backoff(n, 0.5) for n in range(1, 7)] == [0.5, 1.0, 2.0, 4.0, 5.0, 5.0]


@pytest.mark.parametrize(
    "fields",
    [
        {"sql": "DROP TABLE x"},
        {"database": "/etc/passwd"},
        {"provider": "openai"},
        {"task_id": "../q001"},
        {"delay_seconds": 1.0},
        {"demo": "sleep", "delay_seconds": 11.0},
    ],
)
def test_request_rejects_paths_live_providers_and_unbounded_demo(fields):
    with pytest.raises(ValueError):
        JobRequest(**fields)


def test_child_does_not_inherit_secrets_or_pythonpath(monkeypatch, tmp_path):
    monkeypatch.setenv("ARH_WORKFLOW_DATABASE_URL", "synthetic-secret-dsn")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-secret")
    monkeypatch.setenv("PGPASSWORD", "synthetic-db-secret")
    monkeypatch.setenv("ARH_WORKFLOW_AUTH_JSON", "synthetic-auth-secret")
    monkeypatch.setenv("ARH_WORKFLOW_AUTH_FILE", "/private/auth.json")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    env = child_environment(ROOT, tmp_path / "effects.sqlite", os.getpid())
    assert not {"ARH_WORKFLOW_DATABASE_URL", "OPENAI_API_KEY", "PYTHONPATH"} & env.keys()
    assert "synthetic-test-secret" not in json.dumps(env)
    assert "PGPASSWORD" not in env and "synthetic-db-secret" not in json.dumps(env)
    assert "ARH_WORKFLOW_AUTH_JSON" not in env and "ARH_WORKFLOW_AUTH_FILE" not in env


def test_database_configuration_is_local_and_separate(monkeypatch):
    monkeypatch.delenv("ARH_WORKFLOW_DATABASE_URL", raising=False)
    with pytest.raises(ValueError):
        database_url()
    monkeypatch.setenv("ARH_WORKFLOW_DATABASE_URL", "postgresql://local-test")
    monkeypatch.setenv("ARH_WORKFLOW_MODE", "production")
    with pytest.raises(ValueError, match="local"):
        database_url()


def test_provenance_change_is_a_permanent_failure():
    payload = resolved_payload(ROOT, JobRequest())
    payload["provenance"]["script"] = "changed"
    result = execute(ROOT, {"job_id": "test", "attempt": 1, "payload": payload})
    assert result == {"ok": False, "error_code": "provenance_changed", "retryable": False}


def test_synthetic_sink_deduplicates_but_preserves_invocations(tmp_path):
    path = tmp_path / "effects.sqlite"
    assert not synthetic_effect(path, "job", "hash", 1)["deduplicated"]
    assert synthetic_effect(path, "job", "hash", 2)["deduplicated"]
    with pytest.raises(ValueError, match="conflict"):
        synthetic_effect(path, "job", "different", 3)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM effects").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM invocations").fetchone()[0] == 2


@pytest.mark.skipif(os.name == "nt", reason="Native SQL executor requires Linux/Docker")
def test_completed_workflow_can_have_incorrect_agent_answer():
    payload = resolved_payload(ROOT, JobRequest(task_id="q002"))
    result = execute(ROOT, {"job_id": "test", "attempt": 1, "payload": payload})
    assert result["ok"] and result["grade"]["correct"] is False
    assert result["trace"]["events"]


@pytest.mark.skipif(
    not __import__("sys").platform.startswith("linux"),
    reason="Linux process groups and parent-death signaling; use Docker",
)
@pytest.mark.parametrize("reason,timeout", [("attempt_timeout", 0.3), ("lease_lost", 5.0)])
def test_supervisor_kills_and_reaps_its_group(reason, timeout, tmp_path, monkeypatch):
    import subprocess

    import agent_reliability.workflow.worker as worker

    processes = []
    original = subprocess.Popen

    def spawn(*args, **kwargs):
        proc = original(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(worker.subprocess, "Popen", spawn)

    class TestStore:
        policy = Policy(heartbeat_seconds=0.1)

        def heartbeat(self, claim):
            return reason != "lease_lost"

    payload = resolved_payload(ROOT, JobRequest(demo="sleep", delay_seconds=5.0))
    claim = Claim("supervisor-test", 1, "token", "test", payload, timeout)
    result = supervise(TestStore(), claim, ROOT, tmp_path / "effects.sqlite", threading.Event())
    assert result["error_code"] == reason
    assert processes[0].poll() is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(processes[0].pid, 0)
    assert digest(payload) == digest(claim.payload)
