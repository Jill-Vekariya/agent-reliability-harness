"""Isolated fake transports only: these tests authorize no real API requests."""

import json
import shutil

import pytest
import yaml
from conftest import ROOT

import agent_reliability.live as live
from agent_reliability.evaluation.review import grouped_split, review_packet
from agent_reliability.evaluation.tasks import load_tasks, task_hash
from agent_reliability.providers.budget import BudgetExceeded
from agent_reliability.providers.fixture import FixtureProvider
from agent_reliability.runner import environment_manifest
from agent_reliability.tracing.recording import load_trace, save_trace
from agent_reliability.util import digest, file_hash, write_json

TEST_APPROVAL = {"notice": "SYNTHETIC FREEZE TEST ONLY; no real authorization"}


class FakeLiveProvider(FixtureProvider):
    origin = "live"

    def __init__(self):
        super().__init__(
            [
                {
                    "name": "run_sql",
                    "arguments": {"sql": "SELECT COUNT(*) AS artist_count FROM Artist"},
                },
                {"name": "final_answer", "arguments": {"status": "answered", "result_id": "r001"}},
            ]
        )


def campaign(tmp_path, monkeypatch, task_ids):
    config = {"id": "FAKE_TEST", "model": "FAKE_TEST_MODEL", "max_output_tokens": 20}
    approval = dict(
        approved_by="SYNTHETIC TEST ONLY",
        approved_at="TEST",
        campaign_id="fake-campaign",
        official_pricing_url="TEST",
        pricing_checked_at="TEST",
        official_context_limit_url="TEST",
        config_hash=digest(config),
        task_hash=task_hash(ROOT),
        model=config["model"],
        provider="openai",
        budget_usd="1",
        per_attempt_budget_usd="1",
        input_usd_per_million="1",
        cached_input_usd_per_million="0.5",
        output_usd_per_million="2",
        provider_context_window_tokens=10000,
        task_ids=task_ids,
        max_attempts=10,
    )
    path = tmp_path / "synthetic-approval.json"
    write_json(path, approval)
    monkeypatch.setenv("API_BUDGET_USD", "1")
    monkeypatch.setenv("ARH_ARTIFACT_DIR", str(tmp_path / "artifacts"))
    return config, path, tmp_path / "artifacts/live/fake-campaign"


def test_interrupt_checkpoint_and_resume_keep_missing_attempt_without_replacement(
    tmp_path, monkeypatch
):
    config, approval, run_dir = campaign(tmp_path, monkeypatch, ["q001", "q002"])

    def interrupted(*args):
        raise KeyboardInterrupt("Synthetic interruption before dispatch")

    monkeypatch.setattr(live, "OpenAIProvider", interrupted)
    with pytest.raises(KeyboardInterrupt):
        live.run_live(ROOT, config, approval, "dev", 1)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["origin"] == "live" and summary["rows"] == []
    assert summary["coverage"] == {
        "planned": 2,
        "reported": 0,
        "started_without_report": 1,
        "not_started": 1,
    }
    assert len(summary["missing_or_interrupted"]) == 2
    calls = []

    def fake(*args):
        calls.append(args[-1])
        return FakeLiveProvider()

    monkeypatch.setattr(live, "OpenAIProvider", fake)
    result = live.run_live(ROOT, config, approval, "dev", 1, resume=run_dir)
    assert calls == ["fake-campaign:q002:0"]
    assert result["coverage"] == {"planned": 2, "reported": 1, "missing": 1}
    assert "q001" in result["missing_or_interrupted"][0]
    live.run_live(ROOT, config, approval, "dev", 1, resume=run_dir)
    assert len(calls) == 1


def test_completed_fake_campaign_cannot_resume_with_swapped_trace(tmp_path, monkeypatch):
    config, approval, run_dir = campaign(tmp_path, monkeypatch, ["q001"])
    monkeypatch.setattr(live, "OpenAIProvider", lambda *args: FakeLiveProvider())
    result = live.run_live(ROOT, config, approval, "dev", 5)
    assert result["coverage"] == {"planned": 5, "reported": 5, "missing": 0}
    summary = json.loads((run_dir / "summary.json").read_text())
    assert len({r["attempt_id"] for r in summary["rows"]}) == 5
    assert all(r["correct"] for r in summary["rows"])
    path = run_dir / "traces/q001-0.json"
    save_trace(path, load_trace(path).model_copy(update={"task_id": "q002"}))
    with pytest.raises(ValueError, match="provenance"):
        live.run_live(ROOT, config, approval, "dev", 5, resume=run_dir)


def synthetic_frozen_root(tmp_path):
    """A hypothetical unexposed one-task corpus, kept only in pytest's temp dir."""
    for directory in ("src", "data"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copyfile(ROOT / "uv.lock", tmp_path / "uv.lock")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "experiments").mkdir()
    task = load_tasks(ROOT)[0].model_dump()
    task.update(
        id="private_test_fixture",
        family_id="private_test_family",
        question="Synthetic private count",
        review_status="human_reviewed",
        reviewer="SYNTHETIC_TEST_ONLY",
        split="test",
    )
    (tmp_path / "tasks/unit.yaml").write_text(yaml.safe_dump([task]))
    write_json(tmp_path / "tasks/splits.json", {"assignments": {task["id"]: "test"}})
    write_json(tmp_path / "tasks/development_exposure.json", {"task_ids": []})
    packet = review_packet(tmp_path)
    packet["reviews"][0].update(
        reviewer_id="SYNTHETIC_TEST_ONLY",
        status="accept",
        review_date="2026-10-18",
        sql_correct=True,
        expected_outcome_verified=True,
        difficulty=task["difficulty"],
        category=task["category"],
        clarification_needed=False,
        notes="Synthetic fixture; no real review",
    )
    write_json(tmp_path / "review.json", packet)
    write_json(tmp_path / "split.json", grouped_split(tmp_path, test_fraction=0.9))
    config = {"id": "TEST", "model": "FAKE_TEST_MODEL"}
    manifest = environment_manifest(tmp_path, config)
    freeze = {
        key: manifest[key]
        for key in (
            "source_hash",
            "dependency_lock_hash",
            "task_hash",
            "database_manifest_hash",
            "split_hash",
        )
    }
    freeze.update(
        schema_version=1,
        frozen=True,
        approved_by="SYNTHETIC_TEST_ONLY",
        approved_at="TEST",
        config_hashes=[digest(config)],
        approval_hashes=[digest(TEST_APPROVAL)],
        review_packet_path="review.json",
        review_packet_sha256=file_hash(tmp_path / "review.json"),
        split_manifest_path="split.json",
        split_manifest_sha256=file_hash(tmp_path / "split.json"),
    )
    write_json(tmp_path / "experiments/freeze.json", freeze)
    return config


def test_headline_requires_matching_review_split_and_frozen_source(tmp_path):
    config = synthetic_frozen_root(tmp_path)
    live.validate_headline_freeze(tmp_path, config, 5, approval=TEST_APPROVAL)
    with pytest.raises(BudgetExceeded, match="five fresh"):
        live.validate_headline_freeze(tmp_path, config, 4, approval=TEST_APPROVAL)
    with pytest.raises(BudgetExceeded, match="Configuration"):
        live.validate_headline_freeze(
            tmp_path, {**config, "model": "different"}, 5, approval=TEST_APPROVAL
        )
    with pytest.raises(BudgetExceeded, match="Approval/pricing"):
        live.validate_headline_freeze(tmp_path, config, 5, approval={"changed": True})
    (tmp_path / "src/agent_reliability/cli.py").write_text("# altered source\n")
    with pytest.raises(BudgetExceeded, match="source_hash"):
        live.validate_headline_freeze(tmp_path, config, 5, approval=TEST_APPROVAL)


def test_headline_rejects_public_dev_relabeling_even_with_matching_file_hashes(tmp_path):
    config = synthetic_frozen_root(tmp_path)
    write_json(tmp_path / "tasks/development_exposure.json", {"task_ids": ["private_test_fixture"]})
    split_path = tmp_path / "split.json"
    split = grouped_split(tmp_path, test_fraction=0.9)
    split["assignments"]["private_test_fixture"] = "test"
    split["actual_test_count"] = 1
    write_json(split_path, split)
    freeze_path = tmp_path / "experiments/freeze.json"
    freeze = json.loads(freeze_path.read_text())
    freeze["split_manifest_sha256"] = file_hash(split_path)
    write_json(freeze_path, freeze)
    with pytest.raises(BudgetExceeded, match="grouped split"):
        live.validate_headline_freeze(tmp_path, config, 5, approval=TEST_APPROVAL)


def test_current_repository_has_no_eligible_headline_freeze():
    with pytest.raises(BudgetExceeded, match="reviewed corpus"):
        live.validate_headline_freeze(ROOT, {"id": "test"}, 5)
