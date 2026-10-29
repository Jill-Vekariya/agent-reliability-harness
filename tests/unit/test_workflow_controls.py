"""Fail-closed identity and API boundary checks that require no database."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_reliability.workflow.api import create_app, safe_result
from agent_reliability.workflow.auth import DemoAuth, Principal
from agent_reliability.workflow.models import JobRequest

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "unit-tenant-a-token-0000000000"
AUTH = DemoAuth({TOKEN: Principal("tenant-a", "alice")})


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError("Unauthenticated request reached the database: " + name)


def test_all_data_routes_fail_closed_before_database_access():
    with TestClient(create_app(ROOT, NoDatabase(), AUTH)) as client:
        job = "00000000-0000-0000-0000-000000000001"
        routes = ["/jobs", "/approvals", "/budget", f"/jobs/{job}", f"/approvals/{job}"]
        routes += [
            f"/jobs/{job}/{suffix}" for suffix in ["attempts", "result", "trace", "operations"]
        ]
        for route in routes:
            response = client.get(route)
            assert response.status_code == 401
            assert response.headers["Cache-Control"] == "no-store"
        for route, body in [
            ("/jobs", {}),
            (f"/jobs/{job}/cancel", {}),
            (
                f"/approvals/{job}/decision",
                {"decision": "approved", "action_hash": "0" * 64, "action_version": 1},
            ),
        ]:
            assert (
                client.post(route, json=body, headers={"Idempotency-Key": "unit"}).status_code
                == 401
            )
        assert client.get("/live").status_code == 200


def test_startup_requires_explicit_valid_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("ARH_WORKFLOW_AUTH_FILE", raising=False)
    monkeypatch.delenv("ARH_WORKFLOW_AUTH_JSON", raising=False)
    with pytest.raises(ValueError, match="AUTH_FILE"):
        create_app(ROOT, NoDatabase())
    for credentials in [
        {},
        {"short": Principal("tenant-a", "alice")},
        {TOKEN: Principal("../tenant", "alice")},
        {TOKEN: Principal("tenant-a", "alice", "yes")},
    ]:
        with pytest.raises(ValueError):
            DemoAuth(credentials)
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({TOKEN: {"tenant_id": "tenant-a", "subject": "alice"}}))
    monkeypatch.setenv("ARH_WORKFLOW_AUTH_FILE", str(path))
    assert DemoAuth.from_env()


def test_approver_permission_comes_from_authenticated_context():
    with TestClient(create_app(ROOT, NoDatabase(), AUTH)) as client:
        response = client.post(
            "/approvals/00000000-0000-0000-0000-000000000001/decision",
            json={"decision": "approved", "action_hash": "0" * 64, "action_version": 1},
            headers={"Authorization": "Bearer " + TOKEN, "X-Can-Approve": "true"},
        )
        assert response.status_code == 403


def test_trace_redaction_omits_raw_and_future_fields():
    secret = "sensitive-unit-content"
    view = safe_result(
        {
            "ok": True,
            "unexpected": secret,
            "grade": {"correct": True, "detail": secret},
            "trace": {
                "prompt": secret,
                "tool_calls": [secret],
                "events": [{"rows": secret}],
                "future": secret,
            },
        }
    )
    assert secret not in json.dumps(view)
    assert view["trace"] == {"event_count": 1, "redacted": True}
    assert view["grade"] == {"correct": True}


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "openai"},
        {"tenant_id": "tenant-b"},
        {"fake_usage": "missing_usage"},
        {"demo": "provider", "delay_seconds": 11},
    ],
)
def test_control_inputs_remain_bounded_and_cannot_enable_live_providers(body):
    with pytest.raises(ValueError):
        JobRequest(**body)


def test_credential_generator_never_prints_or_replaces_credentials(tmp_path):
    import subprocess
    import sys

    script = ROOT / "scripts/configure_workflow.py"
    first = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert first.returncode == 0
    env_path = tmp_path / ".env.workflow"
    auth_path = tmp_path / ".local/workflow-auth.json"
    original = (env_path.read_bytes(), auth_path.read_bytes())
    credentials = json.loads(original[1])
    assert len(credentials) == 3
    assert all(token not in first.stdout + first.stderr for token in credentials)
    second = subprocess.run(
        [sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True
    )
    assert second.returncode != 0
    assert original == (env_path.read_bytes(), auth_path.read_bytes())


def test_auth_only_upgrade_preserves_stage1_database_password(tmp_path):
    import subprocess
    import sys

    env = tmp_path / ".env.workflow"
    original = "ARH_WORKFLOW_DB_PASSWORD=synthetic-existing-password\n"
    env.write_text(original)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/configure_workflow.py"), "--auth-only"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert env.read_text().startswith(original)
    assert "ARH_WORKFLOW_AUTH_JSON=" in env.read_text()
    assert "synthetic-existing-password" not in result.stdout + result.stderr
