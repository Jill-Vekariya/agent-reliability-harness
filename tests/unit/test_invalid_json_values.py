from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_reliability.workflow.api import create_app
from agent_reliability.workflow.auth import DemoAuth, Principal


class NoDatabase:
    def __getattr__(self, name):
        raise AssertionError("Invalid request reached the database: " + name)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_job_returns_validation_error(number):
    token = "unit-tenant-a-token-0000000000"
    auth = DemoAuth({token: Principal("tenant-a", "alice")})
    with TestClient(create_app(Path.cwd(), NoDatabase(), auth)) as client:
        response = client.post(
            "/jobs",
            content='{"demo":"sleep", "delay_seconds":' + number + "}",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
                "Idempotency-Key": "invalid-job",
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "delay_seconds"]
    assert "input" not in response.json()["detail"][0]
