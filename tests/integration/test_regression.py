from conftest import ROOT

from agent_reliability.models import SQLResult
from agent_reliability.runner import run_offline
from agent_reliability.sandbox import Sandbox


def test_fixed_twenty_task_gate(tmp_path):
    result = run_offline(ROOT, artifact_root=tmp_path)
    assert result["gate_passed"]
    assert result["ordinary_attempts"] == 20
    assert result["ordinary_successes"] == 19  # One explicitly scripted schema failure.
    assert result["live_measurements"] == 0


def test_changed_tool_output_requires_matching_recording(tmp_path, monkeypatch):
    actual = Sandbox.run

    def changed(self, sql):
        return (
            SQLResult(ok=True, columns=["artist_count"], rows=[[999]])
            if sql == "SELECT COUNT(*) AS artist_count FROM Artist"
            else actual(self, sql)
        )

    monkeypatch.setattr(Sandbox, "run", changed)
    result = run_offline(ROOT, artifact_root=tmp_path)
    assert not result["gate_passed"]
    assert "q001" in result["incompatible"]
