import pytest
from conftest import ROOT

from agent_reliability.models import SQLResult
from agent_reliability.runner import run_offline
from agent_reliability.sandbox import Sandbox
from agent_reliability.tracing.recording import RecordedProvider, RecordingMismatch


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


def test_resume_cannot_turn_incompatible_attempt_into_green_gate(tmp_path, monkeypatch):
    original = RecordedProvider.complete

    def mismatch(self, request):
        if "List the first five artists" in request["messages"][1]["content"]:
            raise RecordingMismatch("Injected cache compatibility fault")
        return original(self, request)

    monkeypatch.setattr(RecordedProvider, "complete", mismatch)
    first = run_offline(ROOT, artifact_root=tmp_path)
    assert not first["gate_passed"] and "q002" in first["incompatible"]
    from pathlib import Path

    resumed = run_offline(ROOT, artifact_root=tmp_path, resume=Path(first["run_dir"]))
    assert not resumed["gate_passed"] and "q002" in resumed["incompatible"]


def test_empty_suite_and_escaped_recording_path_are_rejected(tmp_path, monkeypatch):
    import json

    baseline = json.loads((ROOT / "tests/regression/baseline.json").read_text())
    path = tmp_path / "baseline.json"
    monkeypatch.setenv("ARH_BASELINE_FILE", str(path))
    baseline["suite_ids"] = []
    path.write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="suite"):
        run_offline(ROOT, artifact_root=tmp_path / "out")
    baseline["suite_ids"] = ["q001"]
    baseline["entries"][0]["path"] = "../outside.json"
    path.write_text(json.dumps(baseline))
    with pytest.raises(ValueError, match="path"):
        run_offline(ROOT, artifact_root=tmp_path / "out")


def test_resumed_replay_remains_anchored_to_trusted_bytes(tmp_path):
    from pathlib import Path

    from agent_reliability.tracing.recording import load_trace, save_trace

    result = run_offline(ROOT, mode="replay", artifact_root=tmp_path)
    run_dir = Path(result["run_dir"])
    path = run_dir / "traces/q001.json"
    save_trace(path, load_trace(path).model_copy(update={"latency_ms": 999.0}))
    with pytest.raises(ValueError, match="trusted recording"):
        run_offline(ROOT, mode="replay", artifact_root=tmp_path, resume=run_dir)
